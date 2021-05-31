
local DEFAULTS = {
  runtime_name: 'org.freedesktop.Sdk',
  runtime_arch: 'x86_64',
  runtime_branch: '20.08',
  extension_base_name: 'org.freedesktop.Sdk.Extension',
  extension_mount_point: '/usr/lib/sdk',
};

{
  local Enve = self,

  // Template function for ENVE ID objects
  NewId(name, version=''):: {
    assert std.isString(name): 'ENVE ID name must be a string.',
    assert std.isString(version): 'ENVE ID version must be a string when specified.',

    name: name,
    version: version
  },

  // The default ENVE ID
  id: Enve.NewId('ENVE Base', '05.31.2021'),

  // Template function for ENVE variables
  NewVariable(name, values='', values_are_paths=true, delimiter=':', delimit_first=false, exports=''):: {
    assert std.isString(name): 'Variable name must be a string.',
    assert std.isString(values) || std.isArray(values):
      'Variable values must be a string or string array.',
    assert std.isBoolean(values_are_paths): 'Values are paths must be a boolean value.',
    assert std.isString(delimiter): 'Delimiter must be a string when specified.',
    assert std.isBoolean(delimit_first): 'Delimit first must be a boolean value.',
    assert std.isString(exports) || std.isArray(exports):
      'Exports values must be a string or string array.',

    name: name,
    values: if std.isArray(values) then values else [values],
    values_are_paths: values_are_paths,
    delimiter: delimiter,
    delimit_first: delimit_first,
    exports: if std.isArray(exports) then exports else [exports],
  },

  // List of global ENVE variables
  variables: [ ],

  // Template function for flatpak extension objects
  NewExtension(id, id_alias='', commit='current_installed',
    extension_base_name=DEFAULTS.extension_base_name,
    extension_mount_point=DEFAULTS.extension_mount_point,
    remote_name='', variables=[]):: {
      assert std.isString(id): 'Extension ID must be a string.',
      assert std.isString(id_alias): id + ' alias must be a string when specified.',
      assert std.isString(commit): id + ' commit must be a string when specified.',
      assert commit != '': id + ' commit value must be specified.',
      assert std.isString(extension_base_name): 'Extension base name must be a string.',
      assert std.isString(extension_mount_point): 'Extension mount point must be a string.',
      assert std.isString(remote_name): 'Extension remote name must be a string.',
      assert std.isArray(variables): 'Extension variables must be an array of Enve.NewVariables.',

      id: id,
      id_alias: if id_alias != '' then id_alias else id,
      commit: commit,
      path: extension_mount_point + '/' + id,
      flatpak: extension_base_name + '.' + id + '/' + DEFAULTS.runtime_arch + '/' + DEFAULTS.runtime_branch,
      remote_name: remote_name,
      variables: variables,
  },

  // List of ENVE flatpak extensions
  extensions: [ ],

  NewBaseExtensionVersion(commit='current_installed', remote_name='')::
    assert std.isString(commit): 'Base extension commit must be a string.';
    assert std.isString(remote_name): 'Base extension remote name must be a string.';

    Enve.NewExtension('enve',
      commit=commit,
      remote_name=remote_name,
      variables=[
        Enve.NewVariable('BIN', 'bin', exports='PATH'),
        Enve.NewVariable('LIB', 'lib'),
      ]),

  base_extension_version: Enve.NewBaseExtensionVersion(),
}
