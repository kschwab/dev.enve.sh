#!/usr/bin/python3

import os
import re
import click
import json
import _jsonnet
import subprocess
import logging
import configparser
import pprint
import textwrap

def extension_verify_installed(flatpak_extension: dict) -> bool:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # We have to run flatpak commands in the host environment. A return code of 0 from flatpak info indicates
    # the extension is installed.
    if subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'info', flatpak_extension['flatpak']],
                      capture_output=True).returncode != 0:
        logger.warning('%s-%s extension missing, installing...', flatpak_extension['name'],
                       flatpak_extension['version'])

        # The extension is missing, so attempt to install. A return code of 0 means it installed successfully.
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'install', '--user',
                                           flatpak_extension['flatpak']], capture_output=True, text=True)
        if completed_output.returncode != 0:
            # The installation of the extension failed, meaning we can't load the specified environment and will
            # have to abort.
            logger.error('%s-%s extension install failed:\n%s', flatpak_extension['name'], flatpak_extension['version'],
                         textwrap.indent(completed_output.stderr, '  '))
            return False

        logger.info('%s-%s extension install succeeded.', flatpak_extension['name'], flatpak_extension['version'])

    return True

def extension_verify_commit(flatpak_extension: dict) -> bool:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # Verify the installed flatpak extension matches the commit SHA if specified.
    if flatpak_extension['commit'] != None:

        # Get the flatpak extension commit SHA
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'info', '--show-commit'],
                                          capture_output=True, text=True)
        # We already verified the extension is installed earlier, so expect the flatpak query to succeed.
        if completed_output.returncode != 0:
            logger.error('Unable to get info for %s-%s:\n%s', flatpak_extension['name'], flatpak_extension['version'],
                         textwrap.indent(completed_output.stderr, '  '))
            return False

        # If the commit SHA does not match the currently installed commit SHA, update the installed flatpak to
        # the specified commit SHA.
        if flatpak_extension['commit'] != completed_output.stdout.strip()[:len(flatpak_extension['commit'])]:
            logger.warning('%s-%s installed commit mismatch, updating...', flatpak_extension['name'],
                           flatpak_extension['version'])

            # Update the installed flatpak to the specified commit SHA
            completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'update', '--commit=',
                                               flatpak_extension['commit'], flatpak_extension['flatpak']],
                                              capture_output=True, text=True)
            if completed_output.returncode != 0:
                # The update of the extension failed, meaning we can't load the specified environment and will
                # have to abort loading the environment.
                logger.error('%s-%s extension update failed:\n%s', flatpak_extension['name'],
                             flatpak_extension['version'], textwrap.indent(completed_output.stderr, '  '))
                return False

            logger.info('%s-%s extension install succeeded.', flatpak_extension['name'], flatpak_extension['version'])

    return True

def extension_add_paths(flatpak_extension: dict, load_directories: list, project_environ: dict) -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # For each directory in the load directories, check to see if the path exists for the Project extension
    for directory in load_directories:

        # If the path exists for the Project extension, add the path to the dictionary to later be exported into the
        # environment
        flatpak_extension_path = os.path.join(flatpak_extension['path'], directory)
        if os.path.exists(flatpak_extension_path):

            # Add to project specific path environment variable
            flatpak_extension_path_env_var = '_'.join(['PROJECT', flatpak_extension['name'], directory, 'PATH']).upper()
            if flatpak_extension_path_env_var in project_environ:
                project_environ[flatpak_extension_path_env_var].insert(0, flatpak_extension_path)
            else:
                project_environ[flatpak_extension_path_env_var] = [flatpak_extension_path]

            # Add to project cumulative path environment variable
            project_path_env_var = '_'.join(['PROJECT', directory, 'PATH']).upper()
            if project_path_env_var in project_environ:
                project_environ[project_path_env_var].insert(0, flatpak_extension_path)
            else:
                project_environ[project_path_env_var] = [flatpak_extension_path]

    logger.debug('Project Environment Variables:\n%s', textwrap.indent(pprint.pformat(project_environ), '  '))

def load_environ_config(project_config: str) -> [int, dict]:
    '''Add doc...'''

    # Initialize the project environment dictionary
    project_environ = { }
    # Get the logger instance
    logger = logging.getLogger(__name__)

    # If the project_config file is not specified via the command line or environment variable, check to see if it
    # exists in git root directory (if we're in a git repo).
    if not project_config:

        # Get the git root directory, where a return code of zero means we're not in a git repo.
        completed_output = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if completed_output.returncode == 0:

            # Check to see if the project_config.jsonnet file exists in the git root directory.
            git_root_path_project_config = os.path.join(completed_output.stdout.strip(), 'project_config.jsonnet')
            if os.path.exists(git_root_path_project_config):
                project_config = git_root_path_project_config

    # If no project_config file was specified, we must abort with error
    if not project_config:
        if click.confirm('Unable to locate Project config. Would you like you use the base environment?', default=True):
            return 0, project_environ
        else:
            logger.error('Unable to locate Project config.')
            return 1, project_environ

    # Jsonnet will validate the content for us and assert if anything is invalid.
    json_obj = json.loads(_jsonnet.evaluate_file(project_config))
    load_directories = json_obj['Project']['Environment']['Flatpak']['Constant']['EXTENSION_LOAD_DIRECTORIES']

    # Ensure all the specified project flatpak extensions are installed with the right commit versions if
    # specified.
    for flatpak_extension in json_obj['Project']['Environment']['Flatpak']['Extensions']:
        logger.info('Verifying Extension: %s', flatpak_extension['flatpak'])
        logger.debug('%s:\n%s', flatpak_extension['flatpak'],
                     textwrap.indent(pprint.pformat(flatpak_extension), '  '))

        # Verify the extension is installed, and attempt to install if not found
        if not extension_verify_installed(flatpak_extension):
            logger.error('Project environment load failed.')
            return 1, project_environ

        # Verify the extension commit matches the specified, and attempt to update if SHAs mismatch
        if not extension_verify_commit(flatpak_extension):
            logger.error('Project environment load failed.')
            return 1, project_environ

        # Add the extension load directory paths to the load directories dictionary
        extension_add_paths(flatpak_extension, load_directories, project_environ)

    return 0, project_environ

def run_cmd(cmd: list, project_environ: dict, project_shell: bool, project_enable_detached: bool) -> int:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # First check to see if the command is a flatpak app
    if re.match('\w+\.\w+\.\w+', cmd[0]):
        # Attempt to get the flatpak metadata information
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'info', '--show-metadata', cmd[0]],
                                          capture_output=True, text=True)

        # If we're successful with getting the flatpak metadata information, then proceed with running the flatpak app
        # using flatpak-spawn.
        if completed_output.returncode == 0:

            # If debug shell is enabled, override any other commands and just launch a bash shell inside of the flatpak
            # app with the project environment enabled
            if project_shell:
                if cmd[1:]:
                    logger.warning('Project debug shell enabled, ignoring these provided arguments:\n%s',
                                   textwrap.indent(pprint.pformat(cmd[1:]), '  '))
                cmd = [cmd[0], 'sh']
            else:
                # Get the internal command ran by the flatpak app
                config = configparser.ConfigParser()
                config.read_string(completed_output.stdout)
                cmd.insert(1, config['Application']['command'])

            flatpak_spawn_cmd = ['flatpak-spawn', '--host', 'flatpak', 'run',
                                 '--command=/usr/project/bin/project_exec',
                                 '--runtime=project.dev.image-sdk',
                                 '--filesystem=host',
                                 '--socket=session-bus',
                                 '--allow=devel',
                                 '--allow=multiarch',
                                 '--share=network'] + \
                                 ['--env=%s=%s' % (env_var, ':'.join(project_environ[env_var])) for env_var in project_environ]
            flatpak_spawn_cmd += ['--parent-pid=%d' % os.getpid(), '--die-with-parent'] if not project_enable_detached else []

            logger.debug('Exec Command:\n%s', textwrap.indent(pprint.pformat(flatpak_spawn_cmd + cmd), '  '))

            # Run the app using flatpak-spawn under the host system
            if project_enable_detached:
                if project_shell:
                    logger.warning('Cannot run detached when debug shell is enabled. Disabling flatpak app detachment.')
                else:
                    # When running detached we have to use the subprocess.Popen method in order to gain access to the
                    # start_new_session flag
                    subprocess.Popen(flatpak_spawn_cmd + cmd, start_new_session=True)
                    return 0

            # Run the command to completion
            return subprocess.run(flatpak_spawn_cmd + cmd).returncode
        else:
            # Log a warning about using suspected flatpak command as regular system command
            logger.warning('Command "%s" suspected as flatpak app but not found.', cmd[0])
            logger.warning('Treating "%s" as regular system command.', cmd[0])

    # The command does not appear to be a flatpak app, so we'll just run the command here locally without spawning a new
    # flatpak session.

    # Export the project environment variables into the current environment
    for env_var in project_environ:
        os.environ[env_var] = ':'.join(project_environ[env_var])

    # Update the cmd to use the project exec script to run
    cmd.insert(0, '/usr/project/bin/project_exec')

    # If debug shell is enabled, override any other commands and just launch a bash shell in the current environment
    if project_shell:
        if cmd[1:]:
            logger.warning('Project debug shell enabled, ignoring these provided arguments:\n%s',
                           textwrap.indent(pprint.pformat(cmd[1:]), '  '))
        cmd = [cmd[0], 'sh']

    # Run the command to copmletion
    logger.debug('Exec Command:\n%s', textwrap.indent(pprint.pformat(cmd), '  '))
    return subprocess.run(cmd).returncode

@click.command(context_settings={"ignore_unknown_options": True}, no_args_is_help=True)
@click.option('--project_config', envvar='PROJECT_CONFIG', type=click.Path(exists=True),
              help='''Path to project configuration jsonnet file. If not specified, the PROJECT_CONFIG environment
              variable will first be checked, followed by the "project_config.jsonnet" file in the git
              root directory.''')
@click.option('--project_base_environ', is_flag=True,
              help='''If set, will use the project dev base environment.''')
@click.option('--project_shell', is_flag=True,
              help='''Opens a debug shell in the dev environment. Note, this may discard some provided arguments
              when entering the environment.''')
@click.option('--project_verbose', type=click.Choice(['warning', 'info', 'debug']), default='warning',
              help='Set the verbose level. Default is "warning".')
@click.option('--project_enable_detached', is_flag=True,
              help='''Enables a flatpak app to run detached from the project.dev.environ app. Note, the detached
              flatpak app will still retain and use the dev environment sandbox. The "detachment" is only accomplished
              from a system process point of view.''')
@click.argument('cmd', nargs=-1)
def cli(project_config: str, project_base_environ: bool, project_shell: bool, project_verbose: str,
        project_enable_detached: bool, cmd: tuple) -> None:
    '''Add doc...'''

    # Set the logging default level and format
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

    # Get the logger instance
    logger = logging.getLogger(__name__)
    # Set the default log level
    logger.setLevel(logging.WARNING)
    # Update the logger verbosity level if specified
    if 'debug' == project_verbose:
        logger.setLevel(logging.DEBUG)
        logger.info('Debug log level set.')
    elif 'info' == project_verbose:
        logger.setLevel(logging.INFO)
        logger.info('Info log level set.')

    if project_base_environ:
        errno, project_environ = [0, {}]
    else:
        # Parse the environment configs
        errno, project_environ = load_environ_config(project_config)

    # Run the requested cmd using the project environment only if the project environment load was successful
    if errno == 0:
        errno = run_cmd(list(cmd), project_environ, project_shell, project_enable_detached)

    # Exit with error code
    exit(errno)

if __name__ == '__main__':
    cli(prog_name=os.environ['FLATPAK_ID'])
