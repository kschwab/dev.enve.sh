#!/usr/bin/python3

# TODO: Work on a way for developer to have own local config
# TODO: Clean up help
# TODO: Add sandbox option

# NOTE: pty2 lifted and modified from https://github.com/python/cpython/pull/21752/files

import os
ENVE_FLATPAK_APP_ID = 'dev.enve.sh'
ENVE_ROOT_PATH = '/usr/lib/sdk/enve'
ENVE_ETC_PATH = os.path.join(ENVE_ROOT_PATH, 'etc')
ENVE_LIB_PATH = os.path.join(ENVE_ROOT_PATH, 'lib')
ENVE_SRC_PATH = os.path.join(ENVE_ROOT_PATH, 'src')
ENVE_LIBSONNET_PATH = os.path.join(ENVE_ETC_PATH, 'enve.libsonnet')
ENVE_BASE_CONFIG_PATH = os.path.join(ENVE_ETC_PATH, 'enve.jsonnet')
ENVE_BASHRC_PATH = os.path.join(ENVE_ETC_PATH, 'enve_bashrc')
ENVE_PY_PATH = os.path.join(ENVE_SRC_PATH, 'enve.py')
ENVE_RUN_CMD = ('/bin/sh', '--noprofile', '-c')
ENVE_RUN_INTERACTIVE_CMD = ('/bin/sh', '--noprofile', '-i', '-c')

import site
site.addsitedir(os.path.join(ENVE_LIB_PATH, 'python3.8/site-packages'))

import re
import enve_motd
import pty2
import collections
import click
import json
import _jsonnet
import subprocess
import logging
import configparser
import pprint
import textwrap
import psutil
import copy

def add_enve_prompt_variable(enve_vars: dict, enve_options: dict) -> None:
    '''Add doc...'''

    heavy_seperator, light_seperator = ['▌','┆'] if enve_options['use-basic-prompt'].value() else ['', '']
    enve_prompt = r'$(status="$(sha256sum $ENVE_CURRENT_CONFIG | cut -d " " -f 1)"; '
    enve_prompt += r'[[ "$ENVE_CURRENT_CONFIG_SHA_256" = "$status" ]] || '
    enve_prompt += r'echo "\[\e[30;41m\]Modified\[\e[31;42m\]%s")' % heavy_seperator
    enve_prompt += r'\[\e[30;42m\]📦$ENVE_ID${ENVE_ID_VER:+ ${ENVE_ID_VER}}'

    if os.environ['FLATPAK_ID'] != ENVE_FLATPAK_APP_ID:
        enve_prompt += \
            r'\[\e[32;47m\]%s\[\e[30m\]$FLATPAK_ID\[\e[37;49m\]%s' % \
            (heavy_seperator, heavy_seperator)
    else:
        enve_prompt += r'\[\e[32;49m\]%s' % heavy_seperator

    enve_prompt += \
        r'\n\[\e[0;32m\]▍\[\e[0m\]\u@\h \[\e[32m\]%s\[\e[0m\] \W \[\e[32m\]%s\[\e[0m\] $ ' % \
        (light_seperator, light_seperator)

    enve_vars['ENVE_PROMPT'] = enve_prompt

def add_enve_id_version_variables(enve_vars: dict, enve_id: dict) -> None:
    '''Add doc...'''

    enve_vars['ENVE_ID'] = enve_id['name']
    enve_vars['ENVE_ID_VER'] = enve_id['version']

def add_enve_current_config_variables(enve_vars: dict, enve_options: dict) -> None:
    '''Add doc...'''

    enve_vars['ENVE_CURRENT_CONFIG'] = os.path.abspath(enve_options['use-config'].value())
    completed_output = subprocess.run(['sha256sum', enve_options['use-config'].value()], capture_output=True, text=True)
    if completed_output.returncode != 0:
        logger.error('Failure computing sha256sum for %s', enve_options['use-config'].value())
        exit(completed_output.returncode)

    enve_vars['ENVE_CURRENT_CONFIG_SHA_256'] = completed_output.stdout.split()[0]

def add_enve_shell_depth_variable(enve_vars: dict, enve_options: dict) -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    if 'ENVE_SHELL_DEPTH' not in os.environ:
        enve_vars['ENVE_SHELL_DEPTH'] = '0'
    else:
        enve_vars['ENVE_SHELL_DEPTH'] = os.environ['ENVE_SHELL_DEPTH']

def add_enve_flatpak_installation_variable(enve_vars: dict, enve_options: dict) -> None:
    '''Add doc...'''

    if enve_options['use-flatpak-installation'].was_passed() == False and 'ENVE_FLATPAK_INSTALLATION' in os.environ:
        enve_options['use-flatpak-installation'].update_value(os.environ['ENVE_FLATPAK_INSTALLATION'])

    enve_vars['ENVE_FLATPAK_INSTALLATION'] = enve_options['use-flatpak-installation'].value()

def get_flatpak_spawn_cmd(flatpak_spawn_cmd_args: list=[], is_host_cmd: bool=True) -> list:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    flatpak_spawn_cmd = ['flatpak-spawn']
    flatpak_spawn_cmd += [] if not is_host_cmd else ['--host']
    if 'FLATPAK_USER_DIR' in os.environ:
        flatpak_spawn_cmd += ['--env=FLATPAK_USER_DIR=%s' % os.environ['FLATPAK_USER_DIR']]

    logger.debug('Flatpak Spawn Command:\n%s',
                 textwrap.indent(pprint.pformat(flatpak_spawn_cmd + flatpak_spawn_cmd_args), '  '))

    return flatpak_spawn_cmd + flatpak_spawn_cmd_args

def get_flatpak_cmd(enve_options: dict, flatpak_cmd_args: list=[]) -> list:
    '''Add doc...'''

    flatpak_cmd = ['flatpak']
    if enve_options['use-flatpak-installation'].value() in ['user', 'system']:
        flatpak_cmd += ['--%s' % enve_options['use-flatpak-installation'].value()]
    else:
        flatpak_cmd += ['--installation=%s' % enve_options['use-flatpak-installation'].value()]

    return flatpak_cmd + flatpak_cmd_args

def extension_verify_installed(enve_vars: dict, enve_options: dict, flatpak_extension: dict) -> dict:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    verify_results = {'is_installed': True, 'is_new_install': False}

    # We have to run flatpak commands in the host environment. A return code of 0 from flatpak info indicates
    # the extension is installed.
    flatpak_cmd_args = ['info', '--show-origin', flatpak_extension['flatpak']]
    flatpak_spawn_cmd = get_flatpak_spawn_cmd(get_flatpak_cmd(enve_options, flatpak_cmd_args))
    completed_output = subprocess.run(flatpak_spawn_cmd, capture_output=True, text=True)

    is_install_needed = completed_output.returncode != 0
    original_remote_name = '' if is_install_needed else completed_output.stdout.strip()

    # Check to see if we need to re-install the extension from a different remote
    if is_install_needed == False and flatpak_extension['remote_name'] != '':
        if original_remote_name != flatpak_extension['remote_name']:
            logger.warning('"%s" extension is currently installed from remote "%s" instead of "%s". Removing...',
                           flatpak_extension['id'], original_remote_name, flatpak_extension['remote_name'])

            # Extensions can not be removed dynamically as it will affect the container stack. Therefore, only allow
            # extensions to be removed when running outside of a container.
            if 'ENVE_SHELL_DEPTH' in os.environ:
                logger.error('"%s" extension removal failed. Cannot remove extension when inside container.',
                             flatpak_extension['id'])
                logger.error('Try exiting the container first before loading new config "%s".',
                             enve_options['use-config'].value())
                verify_results['is_installed'] = False
                logger.debug('Verify Installed Results: %s' % verify_results)
                return verify_results

            flatpak_spawn_cmd_args = \
                get_flatpak_cmd(enve_options, ['remove', '--assumeyes', flatpak_extension['flatpak']])

            # Remove the current install as it was installed from a different remote than the one specified
            if subprocess.run(get_flatpak_spawn_cmd(flatpak_spawn_cmd_args)).returncode != 0:
                # The installation of the extension failed, meaning we can't load the specified environment and will
                # have to abort.
                logger.error('"%s" extension removal failed.', flatpak_extension['id'])
                verify_results['is_installed'] = False
                logger.debug('Verify Installed Results: %s' % verify_results)
                return verify_results

            is_install_needed = True

    if is_install_needed == True:
        logger.warning('"%s" extension missing, installing...', flatpak_extension['id'])

        # Extract any proxy variables passed as we will need internet access for extension installation
        enve_proxy_vars = \
            ['--env=%s=%s' % (enve_var, enve_vars[enve_var]) \
             for enve_var in enve_vars if re.search('^(https?|ftp|no)_proxy$', enve_var, re.IGNORECASE)]

        flatpak_cmd_args = \
            ['install', '--assumeyes'] + \
            ([flatpak_extension['remote_name']] if flatpak_extension['remote_name'] != '' else []) + \
            [flatpak_extension['flatpak']]

        flatpak_spawn_cmd_args = enve_proxy_vars + get_flatpak_cmd(enve_options, flatpak_cmd_args)
        # The extension is missing, so attempt to install. A return code of 0 means it installed successfully.
        if subprocess.run(get_flatpak_spawn_cmd(flatpak_spawn_cmd_args)).returncode != 0:

            # If the enve extension install failed, try to restore a working copy before dying
            if flatpak_extension['id'] == 'enve' and original_remote_name != '':
                logger.warning('"%s" base extension was removed. Attempt to restore from remote "%s"...',
                               flatpak_extension['id'], original_remote_name)

                flatpak_cmd_args = \
                    ['install', '--assumeyes', original_remote_name, flatpak_extension['flatpak']]
                flatpak_spawn_cmd_args = enve_proxy_vars + get_flatpak_cmd(enve_options, flatpak_cmd_args)
                if subprocess.run(get_flatpak_spawn_cmd(flatpak_spawn_cmd_args), capture_output=True).returncode != 0:
                    logger.warning('"%s" base extension restore from "%s" failed.', flatpak_extension['id'],
                                   original_remote_name)
                else:
                    logger.warning('"%s" base extension was restored from remote "%s".', flatpak_extension['id'],
                                   original_remote_name)

            # The installation of the extension failed, meaning we can't load the specified environment and will
            # have to abort.
            if flatpak_extension['remote_name'] != '':
                logger.error('"%s" extension install from remote "%s" failed.', flatpak_extension['id'],
                             flatpak_extension['remote_name'])
            else:
                logger.error('"%s" extension install failed.', flatpak_extension['id'])

            verify_results['is_installed'] = False
            logger.debug('Verify Installed Results: %s' % verify_results)
            return verify_results

        verify_results['is_new_install'] = True
        logger.info('"%s" extension install succeeded.', flatpak_extension['id'])

    logger.debug('Verify Installed Results: %s' % verify_results)
    return verify_results

def extension_verify_commit(enve_vars: dict, enve_options: dict, flatpak_extension: dict) -> dict:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    verify_results = {'is_installed': True, 'is_new_install': False}

    is_commit_installed = flatpak_extension['commit'] == 'current_installed'

    # Verify the installed flatpak extension matches the commit SHA if specified.
    if is_commit_installed == False and flatpak_extension['commit'] != 'latest':

        # Get the flatpak extension commit SHA
        flatpak_spawn_cmd = get_flatpak_spawn_cmd(get_flatpak_cmd(enve_options, ['info', '--show-commit',
                                                                                 flatpak_extension['flatpak']]))
        completed_output = subprocess.run(flatpak_spawn_cmd, capture_output=True, text=True)
        # We already verified the extension is installed earlier, so expect the flatpak query to succeed.
        if completed_output.returncode != 0:
            logger.error('Unable to get info for %s:\n%s', flatpak_extension['id'],
                         textwrap.indent(completed_output.stderr, '  '))
            verify_results['is_installed'] = False
            logger.debug('Verify Commit Results: %s' % verify_results)
            return verify_results

        # If the commit SHA does not match the currently installed commit SHA, update the installed flatpak to
        # the specified commit SHA.
        is_commit_installed = \
            flatpak_extension['commit'] == completed_output.stdout.strip()[:len(flatpak_extension['commit'])]

    # Update the installed flatpak if the specified commit is not installed or update install was passed
    if is_commit_installed == False or enve_options['update-install'].value() == True:

        # Extension updates to a specific commit can not be done dynamically as it will affect the container
        # stack. Therefore, only allow extensions to be updates to a specific commit when running outside of a
        # container.
        if 'ENVE_SHELL_DEPTH' in os.environ:
            logger.error('"%s" extension update to commit failed. ' +
                         'Cannot update extension to commit when inside container.',
                         flatpak_extension['id'])
            logger.error('Try exiting the container first before loading new config "%s".',
                         enve_options['use-config'].value())
            verify_results['is_installed'] = False
            logger.debug('Verify Commit Results: %s' % verify_results)
            return verify_results

        # Extract any proxy variables passed as we will need internet access for extension installation
        enve_proxy_vars = \
            ['--env=%s=%s' % (enve_var, enve_vars[enve_var]) \
             for enve_var in enve_vars if re.search('^(https?|ftp|no)_proxy$', enve_var, re.IGNORECASE)]

        # Update the flatpak
        flatpak_cmd_args = ['update', '--assumeyes', flatpak_extension['flatpak']]
        if is_commit_installed == False and flatpak_extension['commit'] != 'latest':
            flatpak_cmd_args += ['--commit', flatpak_extension['commit']]
            # If update install was not passed, warn that we found a commit mismatch and are updating
            if enve_options['update-install'].value() == False:
                logger.warning('%s installed commit mismatch, updating...', flatpak_extension['id'])

        flatpak_spawn_cmd_args = enve_proxy_vars + get_flatpak_cmd(enve_options, flatpak_cmd_args)
        if subprocess.run(get_flatpak_spawn_cmd(flatpak_spawn_cmd_args)).returncode != 0:
            # The update of the extension failed, meaning we can't load the specified environment and will
            # have to abort loading the environment.
            logger.error('"%s" extension update failed.', flatpak_extension['id'])
            verify_results['is_installed'] = False
            logger.debug('Verify Commit Results: %s' % verify_results)
            return verify_results

        verify_results['is_new_install'] = True
        logger.info('"%s" extension update succeeded.', flatpak_extension['id'])

    logger.debug('Verify Commit Results: %s' % verify_results)
    return verify_results

def import_callback(dir_path: str, filename:str) -> [str, str]:
    '''Add doc...'''

    if filename == 'enve.libsonnet':
        with open(ENVE_LIBSONNET_PATH) as enve_libsonnet:
            return ENVE_LIBSONNET_PATH, enve_libsonnet.read()
    else:
        abs_path = os.path.abspath(os.path.join(dir_path, filename))
        with open(abs_path) as enve_libsonnet:
            return abs_path, enve_libsonnet.read()

def load_variables(enve_options: dict, enve_id: dict, variables: list) -> dict:
    '''Add doc...'''

    # Initialize the ENVE variables dictionary
    enve_vars = { 'ENV': ENVE_BASHRC_PATH, 'BASH_ENV': ENVE_BASHRC_PATH }

    # Add the ENVE global variables
    add_variables(enve_vars, variables,
                  # The base path for global variables is the config file directory
                  base_path=os.path.dirname(os.path.abspath(enve_options['use-config'].value())))

    # Add the ENVE id variables
    add_enve_id_version_variables(enve_vars, enve_id)

    # Add the ENVE shell depth variable
    add_enve_shell_depth_variable(enve_vars, enve_options)

    # Add the ENVE prompt variable
    add_enve_prompt_variable(enve_vars, enve_options)

    # Add the ENVE current config variables
    add_enve_current_config_variables(enve_vars, enve_options)

    # Add the ENVE flatpak installation variables
    add_enve_flatpak_installation_variable(enve_vars, enve_options)

    return enve_vars

def add_variables(enve_vars: dict, variables: list, extension_alias: str='', base_path: str='') -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    for variable in variables:
        values = variable['values']
        if variable['values_are_paths'] and base_path:
            for index in range(len(values)):
                if not os.path.isabs(values[index]):
                    values[index] = os.path.abspath(os.path.join(base_path, values[index]))

        value = variable['delimiter'].join(values) if len(values) > 1 else values[0]

        # Ensure that export variable names are not prefixed with 'ENVE_'
        invalid_exports = [export for export in variable['exports'] if export.find('ENVE_') == 0]
        if invalid_exports:
            for invalid_export in inavlid_exports:
                logger.error('ENVE export variable name prefixed with "ENVE_": %s', invalid_export)
            exit(1)

        variable_names = [export for export in variable['exports'] if export != '']
        if extension_alias:
            variable_names += ['_'.join(['ENVE', extension_alias, variable['name']]).upper()]
        else:
            variable_names += ['_'.join(['ENVE', variable['name']]).upper()]

        for variable_name in variable_names:
            if variable['delimiter'] == '':
                enve_vars[variable_name] = value
            elif variable_name in enve_vars:
                enve_vars[variable_name] += variable['delimiter'] + value
            elif variable['delimit_first']:
                enve_vars[variable_name] = variable['delimiter'] + value
            else:
                enve_vars[variable_name] = value

        for variable_name in variable_names:
            if variable_name.find('ENVE_') != 0 and variable['delimiter'] != '':
                os_environ_var = os.environ.get(variable_name, '').strip(variable['delimiter'])
                if os_environ_var != '':
                    enve_vars[variable_name] = \
                        enve_vars[variable_name].replace(variable['delimiter'] + os_environ_var, '')
                    enve_vars[variable_name] += variable['delimiter'] + os_environ_var

def export_variables(enve_vars: dict, is_new_enve_shell_needed: bool) -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    logger.debug('ENVE Variables:\n%s', textwrap.indent(pprint.pformat(enve_vars), '  '))

    # Export the ENVE variables into the current environment only if new shell is not needed
    if is_new_enve_shell_needed == False:
        for enve_var in enve_vars:
            os.environ[enve_var] = enve_vars[enve_var]

def load_enve_config(enve_options: dict) -> dict:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # We always spawn a new shell if we're loading an enve_config from an existing ENVE shell to ensure isolation of the
    # requested command.
    load_results = {'is_new_enve_shell_needed': 'ENVE_ID' in os.environ}

    # If the enve_config file is not specified via the command line, first check to see if environment variable is set.
    if not enve_options['use-config'].value() and 'ENVE_CONFIG' in os.environ:
        enve_options['use-config'].update_value(os.environ['ENVE_CONFIG'])

    # If the enve_config file is not specified via the command line or environment variable, search upwards from the
    # current directory to check if config file exists.
    search_directory = os.path.abspath('.')
    while not enve_options['use-config'].value():
        if os.path.exists(os.path.join(search_directory, 'enve.jsonnet')):
            enve_options['use-config'].update_value(os.path.abspath(os.path.join(search_directory, 'enve.jsonnet')))
        elif not os.path.samefile('/', search_directory):
            search_directory = os.path.dirname(search_directory)
        else:
            break

    # If no enve_config file was specified, prompt user on how to proceed
    if not enve_options['use-config'].value():
        if click.confirm('Unable to locate ENVE config. Use the base environment?', default=True):
            enve_options['use-config'].update_value(ENVE_BASE_CONFIG_PATH)
        else:
            logger.error('Unable to locate ENVE config.')
            exit(1)

    # If the ENVE config path does not exist, exit with error
    if not os.path.exists(enve_options['use-config'].value()):
        logger.error('ENVE config path does not exist: %s', enve_options['use-config'].value())
        exit(1)

    # Jsonnet will validate the content for us and assert if anything is invalid.
    try:
        enve_json = json.loads(_jsonnet.evaluate_file(
            enve_options['use-config'].value(), import_callback=import_callback))['Enve']
    except Exception as err:
        logger.exception('Failed to load ENVE config "%s".', enve_options['use-config'].value())
        exit(1)

    # Load the ENVE variables
    enve_vars = load_variables(enve_options, enve_json['id'], enve_json['variables'])

    # Cannot update install when inside a currently active container
    if enve_options['update-install'].value() == True and 'ENVE_SHELL_DEPTH' in os.environ:
        logger.error('ENVE "update install" cannot be called from within ENVE container.')
        exit(1)

    # Add the ENVE base extension to the front of the list of extensions
    enve_json['extensions'].insert(0, enve_json['base_extension_version'])

    # Ensure all the specified flatpak extensions are installed with the right commit versions if specified.
    for flatpak_extension in reversed(enve_json['extensions']):

        # If the current environment config SHA matches the new config SHA, no need to verify as it's already been
        # verified in a previous session.
        if os.environ.get('ENVE_CURRENT_CONFIG_SHA_256', '') == enve_vars['ENVE_CURRENT_CONFIG_SHA_256']:
            pass

        # Otherwise, only verify the install if a new shell is needed or we're not inside a currently active container.
        elif load_results['is_new_enve_shell_needed'] == True or 'ENVE_SHELL_DEPTH' not in os.environ:
            logger.info('Verifying Extension: %s', flatpak_extension['flatpak'])
            logger.debug('%s:\n%s', flatpak_extension['flatpak'],
                         textwrap.indent(pprint.pformat(flatpak_extension), '  '))

            # Verify the extension is installed, and attempt to install if not found
            verify_installed_results = extension_verify_installed(enve_vars, enve_options, flatpak_extension)
            load_results['is_new_enve_shell_needed'] |= verify_installed_results['is_new_install']
            if not verify_installed_results['is_installed']:
                logger.error('ENVE load failed.')
                exit(1)

            # Verify the extension commit matches the specified, and attempt to update if SHAs mismatch
            verify_commit_results = extension_verify_commit(enve_vars, enve_options, flatpak_extension)
            load_results['is_new_enve_shell_needed'] |= verify_commit_results['is_new_install']
            if not verify_commit_results['is_installed']:
                logger.error('ENVE load failed.')
                exit(1)

        # Add the extension load directory paths to the load directories dictionary
        add_variables(enve_vars, flatpak_extension['variables'], flatpak_extension['id_alias'],
                      flatpak_extension['path'])

    if enve_options['update-install'].value() == True:
        enve_id_version = enve_vars['ENVE_ID']
        if 'ENVE_ID_VER' in enve_vars:
            enve_id_version += ' %s' % enve_vars['ENVE_ID_VER']
        print('%s update install successful.' % enve_id_version)
        logger.info('%s update install successful.' % enve_id_version)
        exit(0)

    export_variables(enve_vars, load_results['is_new_enve_shell_needed'])

    logger.debug('Load Results: %s' % load_results)
    return load_results

def load_cmd_metadata(cmd: list, enve_options: dict) -> configparser.ConfigParser:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    cmd_metadata = configparser.ConfigParser()

    # Metadata only exists if the command is a flatpak app
    if re.match('\w+\.\w+\.\w+', cmd[0]):
        # Attempt to get the flatpak metadata information
        flatpak_spawn_cmd_args = get_flatpak_cmd(enve_options, ['info', '--show-metadata', cmd[0]])
        completed_output = subprocess.run(get_flatpak_spawn_cmd(flatpak_spawn_cmd_args), capture_output=True, text=True)

        # If we're successful with getting the flatpak metadata information, then proceed with running the flatpak app
        # using flatpak-spawn.
        if completed_output.returncode == 0:
            # Get the internal command ran by the flatpak app
            cmd_metadata.read_string(completed_output.stdout)
        else:
            # Log a warning about using suspected flatpak command as regular system command and prompt user on how to
            # proceed
            logger.warning('Command "%s" suspected as flatpak app but not found.', cmd[0])
            if not click.confirm('Treat "%s" as regular system command?' % cmd[0]):
                logger.error('Invalid command "%s" received.' % cmd[0])
                exit(1)

    return cmd_metadata

def run_cmd(cmd: list, enve_options: dict) -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # Load the ENVE config
    load_results = load_enve_config(enve_options)

    # Load the command meta data if the command is a flatpak app. If the command is not a flatpak app,
    # cmd_metadata.sections() will be [], indicating nothing was loaded or found for the supplied command.
    cmd_metadata = load_cmd_metadata(cmd, enve_options)

    # Use flatpak-spawn if a new enve shell is needed for the config
    if cmd_metadata.sections() != [] or load_results['is_new_enve_shell_needed'] == True:

        # If we weren't passed a flatpak app as a command, grab the command meta data from the current flatpak ID.
        if not cmd_metadata.sections():
            cmd_metadata = load_cmd_metadata([os.environ['FLATPAK_ID']], enve_options)
            # Use the flatpak app as the primary command, and supply the desired command as the argument to pass into
            # enve.py when the new environment is spawned.
            cmd.insert(0, os.environ['FLATPAK_ID'])
        else:
            # Use the flatpak app internal command as the argument to pass into enve.py when the new environment is
            # spawned.
            cmd.insert(1, cmd_metadata['Application']['command'])

        # Pass the ENVE options through to the spawned command
        for option in enve_options:
            if enve_options[option].was_passed():
                cmd += ['--ENVE', str(option), str(enve_options[option].value())]

        # Take care of setting the use-config param if it wasn't passed so we don't double prompt the user.
        if not enve_options['use-config'].was_passed():
            cmd += ['--ENVE', 'use-config', enve_options['use-config'].value()]

        # Always ensure that the flatpak installation param is passed.
        if not enve_options['use-flatpak-installation'].was_passed():
            cmd += ['--ENVE', 'use-flatpak-installation', enve_options['use-flatpak-installation'].value()]

        # Always ensure the use-interactive flag is passed when using flatpak-spawn.
        if not enve_options['use-interactive'].was_passed():
            cmd += ['--ENVE', 'use-interactive', 't']

        flatpak_cmd_args = \
            ['run',
             '--command=%s' % ENVE_PY_PATH,
             '--runtime=%s' % cmd_metadata['Application']['sdk'],
             '--filesystem=host',
             '--socket=session-bus',
             '--allow=devel',
             '--allow=multiarch',
             '--share=network',
             '--device=all',
             '--env=ENVE_SHELL_DEPTH=%s' % str(int(os.environ.get('ENVE_SHELL_DEPTH', '0')) + 1),
             '--env=TERM=%s' % os.environ.get('TERM', '')] + cmd
        flatpak_spawn_cmd_args = ['--watch-bus'] + get_flatpak_cmd(enve_options, flatpak_cmd_args)

        # Run the command to completion
        exit(subprocess.run(get_flatpak_spawn_cmd(flatpak_spawn_cmd_args)).returncode)

    cmd_str = ' '.join(cmd)

    if (not enve_options['use-debug-shell'].value()) or click.confirm('Debug shell enabled. Run command "%s"?' % cmd_str):

        # Run the command to completion
        logger.debug('Run Command:\n%s', textwrap.indent(pprint.pformat(cmd), '  '))

        # If the use-interactive flag was not specified, it means we've been invoked directly from the host system using
        # flatpak run (as opposed to flatpak-spawn which will always pass the use-interactive flag). We'll default to
        # using interactive mode for this case as typically host invocation will be called from a CLI. The next most
        # prevalent case will be calls from a host IDE, for which we expect the use-interactive flag to be passed if
        # necessary and set appropriately.
        if (not enve_options['use-interactive'].was_passed()) or enve_options['use-interactive'].value():
            if cmd_str in ['sh', 'bash']:
                enve_motd.print_enve_motd()
            if psutil.Process().terminal() == None:
                # Can't be interactive without a PTY, so create one if it doesn't exist
                errno = pty2.wspawn([*ENVE_RUN_INTERACTIVE_CMD, cmd_str])
            else:
                errno = subprocess.run([*ENVE_RUN_INTERACTIVE_CMD, cmd_str]).returncode
        else:
            errno = subprocess.run([*ENVE_RUN_CMD, cmd_str]).returncode

    if enve_options['use-debug-shell'].value():
        enve_motd.print_enve_motd()
        if psutil.Process().terminal() == None:
            errno = pty2.wspawn([*ENVE_RUN_INTERACTIVE_CMD, 'sh'])
        else:
            errno = subprocess.run([*ENVE_RUN_INTERACTIVE_CMD, 'sh']).returncode

    exit(errno)

def enve_default_options() -> dict:
    '''Add doc...'''

    return dict([(option.name(), copy.deepcopy(option)) for option in ENVE_OPTIONS])

class EnveConfigPath(click.Path):

    def convert(self, value, param, ctx):
        if value.lower() == 'base':
            return ENVE_BASE_CONFIG_PATH
        else:
            return super().convert(value, param, ctx)

class EnveOption:

    def __init__(self, name, default, click_type, help_msg=''):
        self._name = name
        self._value = default
        self._default = default
        self._click_type = click_type
        self._help_msg = help_msg
        self._was_passed = False

    def help_msg(self):
        return self._help_msg

    def default(self):
        return self._default

    def was_passed(self):
        return self._was_passed

    def value(self):
        return self._value

    def name(self):
        return self._name

    def update_value(self, value, ctx=None, was_passed=False):
        try:
            self._value = self._click_type.convert(value, self._name, ctx)
            self._was_passed = self._was_passed or was_passed
        except click.exceptions.ClickException as e:
            # Get the logger instance
            logger = logging.getLogger(__name__)
            logger.error('--ENVE %s %s', self._name, e)
            exit(e.exit_code)

ENVE_OPTIONS = (
    EnveOption('use-config', '', EnveConfigPath(exists=True),
               '''Path to the enve configuration file. If not specified, the ENVE_CONFIG environment variable will first be
               checked, followed by the "enve.jsonnet" file in the git root directory.
               ... If set, will use the ENVE base config for setting up the environment.'''
    ),

    EnveOption('use-verbose', 'warning', click.Choice(['debug', 'info', 'warning']),
               '''Set the verbose level. Default is "warning".'''
    ),

    EnveOption('use-debug-shell', False, click.BOOL,
               '''Opens a debug shell in the environment after running the commands.'''
    ),

    EnveOption('use-interactive', None, click.BOOL,
               '''Add doc.'''
    ),

    EnveOption('use-basic-prompt', False, click.BOOL,
               '''Add doc.'''
    ),

    EnveOption('use-flatpak-installation', 'user', click.STRING,
               '''Add doc.'''
    ),

    EnveOption('update-install', False, click.BOOL,
               '''Add doc.'''
    ),

    # EnveOption('use-sandbox', False, click.BOOL,
    #            '''Add doc.'''
    # )
)

@click.command(context_settings={"ignore_unknown_options": True})
@click.option('--ENVE', type=(click.Choice([option.name() for option in ENVE_OPTIONS]), str), multiple=True)
@click.argument('cmd', nargs=-1)
@click.pass_context
def cli(ctx, cmd: tuple, enve: tuple) -> None:
    '''Add doc...'''

    # Set the logging default level and format
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    # Get the logger instance
    logger = logging.getLogger(__name__)
    # Set the default log level
    logger.setLevel(logging.WARNING)

    # Parse the ENVE options
    enve_options = enve_default_options()
    for opt, value in enve:
        enve_options[opt].update_value(value, ctx, was_passed=True)

    # Update the logger verbosity level if specified
    if 'debug' == enve_options['use-verbose'].value():
        logger.setLevel(logging.DEBUG)
    elif 'info' == enve_options['use-verbose'].value():
        logger.setLevel(logging.INFO)

    # Convert the cmd tuple into a list
    cmd = list(cmd)

    # If no command is specified, start the shell by default
    if not cmd:
        cmd = ['sh']

    # Run the requested shell cmd using ENVE only if the ENVE load was successful
    run_cmd(cmd, enve_options)

if __name__ == '__main__':
    cli(prog_name='enve')
