{
  // Specifications for the Project flatpak development environment
  Flatpak: {

    // Constants associated with the Project flatpak environment
    Constant: {

      // The freedesktop SDK extensions branch
      EXTENSION_BRANCH: '//20.08',

      // The base name for freedesktop SDK extensions
      EXTENSION_BASE_NAME: 'org.freedesktop.Sdk.Extension',

      // The mount point for freedesktop SDK extensions
      EXTENSION_MOUNT_PATH: '/usr/lib/sdk',

      // The extension load directories
      EXTENSION_LOAD_DIRECTORIES: [
        'bin', 'bin32', 'bin64',
        'lib', 'lib32', 'lib64',
        'include', 'include32', 'include64'
      ],
    },

    // Template function for Project flatpak environment extension objects
    Extension(id, enve_alias=null, commit=null):: {
      id: id,

      assert std.isString(enve_alias) || enve_alias == null: id + ' enve alias must be a string.',
      enve_alias: if enve_alias != null then enve_alias else id,

      commit: commit,
      path: $['Flatpak'].Constant.EXTENSION_MOUNT_PATH + '/' + id,
      flatpak: $['Flatpak'].Constant.EXTENSION_BASE_NAME + '.' + id + $['Flatpak'].Constant.EXTENSION_BRANCH,
    },

    // List of Project flatpak environment extensions. Path and link order matter.
    Extensions: [],
  }
}
