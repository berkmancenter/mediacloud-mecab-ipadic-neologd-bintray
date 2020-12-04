#!/usr/bin/env python3

import argparse
import logging
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

logging.basicConfig(level=logging.DEBUG)


class MeCabPackageException(Exception):
    pass


MECAB_IPADIC_NEOLOGD_NAME = "mecab-ipadic-neologd"
MECAB_IPADIC_NEOLOGD_SUMMARY = "Neologism dictionary based on the language resources on the Web for mecab-ipadic"
MECAB_IPADIC_NEOLOGD_LICENSE = "Apache-2.0"
MECAB_IPADIC_NEOLOGD_VENDOR = "Toshinori Sato (@overlast) <overlasting@gmail.com>"
MECAB_IPADIC_NEOLOGD_MAINTAINER = "Linas Valiukas <linas@mediacloud.org>"
MECAB_IPADIC_NEOLOGD_URL = "https://github.com/mediacloud/mecab-ipadic-neologd-prebuilt"
MECAB_IPADIC_NEOLOGD_GIT_URL = MECAB_IPADIC_NEOLOGD_URL + ".git"
MECAB_IPADIC_NEOLOGD_DEPENDS_MECAB_VERSION = "0.996"
MECAB_IPADIC_NEOLOGD_CHANGELOG_FILE = 'ChangeLog'
MECAB_IPADIC_NEOLOGD_TAGS = [
    'mecab-ipadic',
    'named-entities',
    'dictionary',
    'furigana',
    'neologism-dictionary',
    'mecab',
    'language-resources',
    'japanese-language',
]

PATH_TO_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')
MECAB_IPADIC_NEOLOGD_MISC_DOCS = [
    os.path.join(PATH_TO_ROOT, 'README.md'),
    os.path.join(PATH_TO_ROOT, 'README.ja.md'),
    os.path.join(PATH_TO_ROOT, MECAB_IPADIC_NEOLOGD_CHANGELOG_FILE),
    os.path.join(PATH_TO_ROOT, 'COPYING'),
]


# ---

def __run_command(command: List[str], cwd: Optional[str] = None) -> None:
    process = subprocess.Popen(command,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               bufsize=0,
                               cwd=cwd)
    while True:
        output = process.stdout.readline()
        if len(output) == 0 and process.poll() is not None:
            break
        logging.info(output.strip())
    rc = process.poll()
    if rc > 0:
        raise MeCabPackageException(f"Process returned non-zero exit code {rc}")


def __temp_directory() -> str:
    """Return temporary directory on the same partition (to be able to hardlink stuff)."""
    return tempfile.mkdtemp()


def __mkdir_p(path: str) -> None:
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def create_tgz_package(input_dir: str, version: str, revision: str) -> str:
    temp_dir = __temp_directory()
    mecab_dirname = f'{MECAB_IPADIC_NEOLOGD_NAME}-{version}-{revision}'
    temp_mecab_dir_path = os.path.join(temp_dir, mecab_dirname)
    os.mkdir(temp_mecab_dir_path)
    logging.debug(f'Temporary MeCab tarball directory: {temp_mecab_dir_path}')

    logging.info('Linking MeCab files to tarball directory...')
    for filename in os.listdir(input_dir):
        full_filename = os.path.join(input_dir, filename)
        if os.path.isfile(full_filename):
            os.link(full_filename, os.path.join(temp_mecab_dir_path, filename))

    logging.info('Linking documentation files to tarball directory...')
    for doc_file_path in MECAB_IPADIC_NEOLOGD_MISC_DOCS:
        os.link(doc_file_path, os.path.join(temp_mecab_dir_path, os.path.basename(doc_file_path)))

    tarball_filename = f'{mecab_dirname}.tgz'
    logging.info(f'Creating "{tarball_filename}"...')
    temp_mecab_tarball_path = os.path.join(temp_dir, tarball_filename)
    __run_command(['tar', '-czvf', temp_mecab_tarball_path, mecab_dirname], cwd=temp_dir)

    logging.info('Cleaning up temporary directory...')
    shutil.rmtree(temp_mecab_dir_path)

    logging.info(f'Resulting tarball: {temp_mecab_tarball_path}')
    return temp_mecab_tarball_path


def __fpm_common_flags(version: str, revision: str) -> List[str]:
    return [
        '--verbose',
        '--input-type', 'dir',
        '--name', MECAB_IPADIC_NEOLOGD_NAME,
        '--version', version,
        '--iteration', revision,
        '--description', MECAB_IPADIC_NEOLOGD_SUMMARY,
        '--license', MECAB_IPADIC_NEOLOGD_LICENSE,
        '--vendor', MECAB_IPADIC_NEOLOGD_VENDOR,
        '--maintainer', MECAB_IPADIC_NEOLOGD_MAINTAINER,
        '--url', MECAB_IPADIC_NEOLOGD_URL,
        '--architecture', 'all',
        '--prefix', '/',
    ]


def create_deb_package(input_dir: str, version: str, revision: str) -> str:
    temp_dir = __temp_directory()
    deb_source_dir = os.path.join(temp_dir, 'deb')
    os.mkdir(deb_source_dir)

    deb_base_lib_dir = 'var/lib/mecab/dic/ipadic-neologd'
    deb_base_doc_dir = 'usr/share/doc/mecab-ipadic-neologd'

    lib_dir = os.path.join(deb_source_dir, deb_base_lib_dir)
    __mkdir_p(lib_dir)

    doc_dir = os.path.join(deb_source_dir, deb_base_doc_dir)
    __mkdir_p(doc_dir)

    logging.info('Linking MeCab files to library directory...')
    for filename in os.listdir(input_dir):
        full_filename = os.path.join(input_dir, filename)
        if os.path.isfile(full_filename):
            os.link(full_filename, os.path.join(lib_dir, filename))

    logging.info('Linking documentation files to documentation directory...')
    for doc_file_path in MECAB_IPADIC_NEOLOGD_MISC_DOCS:
        os.link(doc_file_path, os.path.join(doc_dir, os.path.basename(doc_file_path)))

    deb_name = f'{MECAB_IPADIC_NEOLOGD_NAME}_{version}-{revision}_all.deb'
    deb_path = os.path.join(temp_dir, deb_name)

    after_install_path = os.path.join(temp_dir, 'after-install')
    with open(after_install_path, 'w') as after_install:
        after_install.write(
            f'update-alternatives --install /var/lib/mecab/dic/debian mecab-dictionary /{deb_base_lib_dir} 100'
        )

    after_remove_path = os.path.join(temp_dir, 'after-remove')
    with open(after_remove_path, 'w') as after_remove:
        after_remove.write(f'update-alternatives --remove mecab-dictionary /{deb_base_lib_dir}')

    logging.info(f'Creating {deb_name}...')
    fpm_command = ['fpm'] + __fpm_common_flags(version=version, revision=revision) + [
        '--output-type', 'deb',
        '--package', deb_path,
        '--chdir', deb_source_dir,
        '--depends', f'mecab (>= {MECAB_IPADIC_NEOLOGD_DEPENDS_MECAB_VERSION})',
        '--category', 'misc',
        '--deb-priority', 'extra',
        '--deb-no-default-config-files',
        '--after-install', after_install_path,
        '--after-remove', after_remove_path,
    ]
    logging.debug(fpm_command)
    __run_command(fpm_command)

    logging.info('Cleaning up temporary directory...')
    shutil.rmtree(deb_source_dir)

    logging.info(f'Resulting .deb: {deb_path}')
    return deb_path


def create_rpm_package(input_dir: str, version: str, revision: str) -> str:
    temp_dir = __temp_directory()
    rpm_source_dir = os.path.join(temp_dir, 'rpm')
    os.mkdir(rpm_source_dir)

    lib_dir = os.path.join(rpm_source_dir, 'usr/lib64/mecab/dic/ipadic-neologd')
    __mkdir_p(lib_dir)

    doc_dir = os.path.join(rpm_source_dir, f'usr/share/doc/{MECAB_IPADIC_NEOLOGD_NAME}-{version}')
    __mkdir_p(doc_dir)

    logging.info('Linking MeCab files to library directory...')
    for filename in os.listdir(input_dir):
        full_filename = os.path.join(input_dir, filename)
        if os.path.isfile(full_filename):
            os.link(full_filename, os.path.join(lib_dir, filename))

    logging.info('Linking documentation files to documentation directory...')
    for doc_file_path in MECAB_IPADIC_NEOLOGD_MISC_DOCS:
        os.link(doc_file_path, os.path.join(doc_dir, os.path.basename(doc_file_path)))

    rpm_name = f'{MECAB_IPADIC_NEOLOGD_NAME}_{version}-{revision}_all.rpm'
    rpm_path = os.path.join(temp_dir, rpm_name)

    logging.info(f'Creating {rpm_name}...')
    fpm_command = ['fpm'] + __fpm_common_flags(version=version, revision=revision) + [
        '--output-type', 'rpm',
        '--package', rpm_path,
        '--chdir', rpm_source_dir,
        '--depends', f'mecab >= {MECAB_IPADIC_NEOLOGD_DEPENDS_MECAB_VERSION}',
        '--category', 'Applications/Text',
        '--rpm-os', 'linux',
    ]
    logging.debug(fpm_command)
    __run_command(fpm_command)

    logging.info('Cleaning up temporary directory...')
    shutil.rmtree(rpm_source_dir)

    logging.info(f'Resulting .rpm: {rpm_path}')
    return rpm_path


def __version_revision_from_version_tag(version_tag: str) -> Tuple[str, str]:
    version, revision = re.split(r'[\-_]', version_tag)
    return version, revision


def create_package(package_type: str, input_dir: str, version: str, revision: str) -> str:
    if not os.path.isfile(os.path.join(input_dir, 'sys.dic')):
        raise MeCabPackageException(f'Input directory "{input_dir}" does not contain build MeCab dictionary.')
    for misc_doc_file in MECAB_IPADIC_NEOLOGD_MISC_DOCS:
        if not os.path.isfile(misc_doc_file):
            raise MeCabPackageException(f'Misc. documentation file "{misc_doc_file}" does not exist.')

    if package_type == 'tgz':
        package_path = create_tgz_package(input_dir=input_dir, version=version, revision=revision)
    elif package_type == 'deb':
        package_path = create_deb_package(input_dir=input_dir, version=version, revision=revision)
    elif package_type == 'rpm':
        package_path = create_rpm_package(input_dir=input_dir, version=version, revision=revision)
    else:
        raise MeCabPackageException(f'Unknown package type "{package_type}".')

    if not os.path.isfile(package_path):
        MeCabPackageException(f'Created package "{package_path}" does not exist.')

    return package_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Package MeCab dictionary.')
    parser.add_argument('--type', required=True, choices=['tgz', 'deb', 'rpm'], help='Package type.')
    parser.add_argument('--input_dir', required=True, help='Input directory with built MeCab dictionary.')
    parser.add_argument('--version_tag', required=True, help='Git version tag (version + revision), e.g. "20170814-1".')
    parser.add_argument('--output_file', required=True, help='Output package file.')

    args = parser.parse_args()

    arg_version, arg_revision = re.split(r'[\-_]', args.version_tag)
    logging.debug(f'Version: {arg_version}, revision: {arg_revision}')

    logging.info(f'Creating "{args.type}" package from "{args.input_dir}"...')
    pkg_path = create_package(package_type=args.type,
                              input_dir=args.input_dir,
                              version=arg_version,
                              revision=arg_revision)

    logging.info(f'Moving package "{pkg_path}" to "{args.output_file}".')
    shutil.move(pkg_path, args.output_file)

    logging.info(f'Package created at "{args.output_file}".')
