from logging import Logger
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

from plumbum import local

from alts.worker import CONFIG


def checkout(git_ref: str, git_repo_path: Path, logger: Logger):
    logger.debug('Switching to the git branch/tag: %s', git_ref)
    exit_code, _, stderr = local['bash'].run(
        ['-c', f'git fetch origin && git checkout {git_ref}'],
        retcode=None,
        cwd=git_repo_path,
    )


def git_reset_hard(git_repo_path: Path, logger: Logger):
    exit_code, _, stderr = local['bash'].run(
        ['-c', 'git checkout master && git reset --hard origin/master'],
        retcode=None,
        cwd=git_repo_path,
    )
    if exit_code != 0:
        logger.error(
            'Cannot reset the git index and working tree:\n%s',
            stderr,
        )


def clone_git_repo(
    repo_url: str,
    git_ref: str,
    work_dir: Path,
    logger: Logger,
) -> Optional[Path]:
    git_repo_path = Path(
        work_dir,
        Path(repo_url).name.replace('.git', ''),
    )
    if git_repo_path.exists():
        logger.debug('The git repo %s has already been clonned', repo_url)
        checkout(git_ref, git_repo_path, logger)
        return git_repo_path
    logger.debug('Cloning the git repo: %s', repo_url)
    exit_code, _, stderr = local['git'].run(
        ['clone', repo_url],
        retcode=None,
        cwd=work_dir,
    )
    if exit_code != 0:
        logger.error(
            'Cannot clone the git repo: %s\n%s',
            repo_url,
            stderr,
        )
        return
    checkout(git_ref, git_repo_path, logger)
    return git_repo_path


def prepare_gerrit_command(git_ref: str) -> str:
    command = ''
    if git_ref == 'master':
        command = 'git checkout master && git pull'
    elif '/' not in git_ref and not git_ref.isdigit():
        command = (
            f'git reset --hard origin/{git_ref} && '
            f'git checkout {git_ref} && git pull'
        )
    elif all(git_ref.split('/')):
        review, patchset = git_ref.split('/')
        sm = review[-2:]
        command = (
            'git pull && '
            f"git fetch origin 'refs/changes/{sm}/{review}/{patchset}'"
            '--force --update-head-ok --progress && '
            'git checkout FETCH_HEAD'
        )
    return command


def prepare_gerrit_repo_url(url: str) -> str:
    parsed = urlparse(url)
    netloc = f'{CONFIG.gerrit_username}@{parsed.netloc}'
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def clone_gerrit_repo(
    repo_url: str,
    git_ref: str,
    work_dir: Path,
    logger: Logger,
) -> Optional[Path]:
    # ssh://gerrit.test.com:00000/repo
    git_repo_path = Path(work_dir, Path(repo_url).name)
    if not git_repo_path.exists():
        logger.debug('Cloning the git repo: %s', repo_url)
        exit_code, _, stderr = local['git'].run(
            ['clone', repo_url],
            retcode=None,
            cwd=work_dir,
        )
        if exit_code != 0:
            logger.error('Cannot clone the git repo: %s\n%s', repo_url, stderr)
            return
    gerrit_command = prepare_gerrit_command(git_ref)
    if not gerrit_command:
        logger.debug('Nothing to do, skipping')
        return
    exit_code, _, stderr = local['bash'].run(
        ['-c', gerrit_command],
        retcode=None,
        cwd=git_repo_path,
    )
    if exit_code != 0:
        logger.error(
            'Cannot execute gerrit command: %s\n%s',
            gerrit_command,
            stderr,
        )
        return
    return git_repo_path