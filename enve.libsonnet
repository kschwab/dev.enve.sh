{
  local Enve = self,

  // Template function for ENVE ID objects
  NewId(name, version=''):: {
    assert std.isString(name): 'ENVE ID name must be a string.',
    assert std.isString(version): 'ENVE ID version must be a string when specified.',

    name: name,
    version: version,
  },

  // The default ENVE ID
  id: Enve.NewId('ENVE Base', '01.01.21'),

  // Template function for Runtime objects
  NewRuntime(name, branch, arch='x86_64', default_extension_base_name='org.freedesktop.Sdk.Extension',
  default_extension_mount_point='/usr/lib/sdk', default_remote_name='flathub'):: {
    assert std.isString(name): 'Runtime name must be a string.',
    assert std.isString(branch): 'Runtime branch must be a string.',
    assert std.isString(arch): 'Runtime arch must be a string.',
    assert std.isString(default_extension_base_name):
      'Runtime default extension base name must be a string when specified.',
    assert std.isString(default_extension_mount_point):
      'Runtime default extension mount point must be a string when specified.',

    name: name,
    arch: arch,
    branch: branch,
    default_extension_base_name: default_extension_base_name,
    default_extension_mount_point: default_extension_mount_point,
    default_remote_name: default_remote_name
  },

  // The default ENVE Flatpak runtime
  runtime: Enve.NewRuntime('org.freedesktop.Sdk', '20.08'),

  // Template function for ENVE variables
  NewVariable(name, values='', values_are_paths=true, delimiter=':', delimit_first=false, path_export=false):: {
    assert std.isString(name): 'Variable name must be a string.',
    assert std.isString(values) || std.isArray(values):
      'Variable values must be a string or string array.',
    assert std.isBoolean(values_are_paths): 'Values are paths must be a boolean value.',
    assert std.isString(delimiter): 'Delimiter must be a string when specified.',
    assert std.isBoolean(delimit_first): 'Delimit first must be a boolean value.',
    assert std.isBoolean(path_export): 'Export path must be a boolean value.',
    assert !path_export || values_are_paths: 'Variable path export values must be paths.',

    name: name,
    values: if std.isArray(values) then values else [values],
    values_are_paths: values_are_paths,
    delimiter: delimiter,
    delimit_first: delimit_first,
    path_export: path_export,
  },

  // List of global ENVE variables
  variables: [
    Enve.NewVariable('ID', Enve.id.name, values_are_paths=false),
    Enve.NewVariable('ID_VER', Enve.id.version, values_are_paths=false),
  ],

  // Template function for flatpak extension objects
  NewExtension(id, id_alias='', commit='', extension_base_name=$['runtime'].default_extension_base_name,
  extension_mount_point=$['runtime'].default_extension_mount_point, remote_name=$['runtime'].default_remote_name,
  proxy='', variables=[]):: {
    assert std.isString(id): 'Extension ID must be a string.',
    assert std.isString(id_alias): id + ' alias must be a string when specified.',
    assert std.isString(commit): id + ' commit must be a string when specified.',
    assert std.isString(extension_base_name): 'Extension base name must be a string.',
    assert std.isString(extension_mount_point): 'Extension mount point must be a string.',
    assert std.isString(remote_name): 'Extension remote name must be a string.',
    assert std.isString(proxy): 'Extension proxy must be a string.',
    assert std.isArray(variables): 'Extension variables must be an array of Enve.NewVariables.',

    id: id,
    id_alias: if id_alias != '' then id_alias else id,
    commit: commit,
    path: extension_mount_point + '/' + id,
    flatpak: extension_base_name + '.' + id + '/' + $['runtime'].arch + '/' + $['runtime'].branch,
    remote_name: remote_name,
    proxy: proxy,
    variables: variables,
  },

  // List of ENVE flatpak extensions
  extensions: [
    Enve.NewExtension('enve', variables=[
      Enve.NewVariable('BIN', 'bin', path_export=true),
      Enve.NewVariable('LIB', 'lib'),
    ]),
  ],
}
