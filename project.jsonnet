{
  // Project development environment types and specifications
  Environment: {

    // Specifications for the Project flatpak development environment
    Flatpak: {

      // Constants associated with the Project flatpak environment
      Constant: {

        // The default branch used by Project flatpak environment extensions
        EXTENSION_BRANCH: '//20.08',

        // The base name for Project flatpak environment extensions
        EXTENSION_BASE_NAME: 'project.dev.environ.extension',

        // The mount point for Project flatpak environment extensions
        EXTENSION_MOUNT_PATH: '/usr/project/extensions',

        // The extension load directories
        EXTENSION_LOAD_DIRECTORIES: [
          'bin', 'bin32', 'bin64',
          'lib', 'lib32', 'lib64',
          'include', 'include32', 'include64'
        ],
      },

      // Template function for Project flatpak environment extension objects
      Extension(name, version, commit=null):: {
        // Jsonnet standard lib documentation can be found here: https://jsonnet.org/ref/stdlib.html

        assert std.findSubstr('-', name)  == []: 'Dashes not allowed in extension name: ' + name,
        assert std.findSubstr('.', name)  == []: 'Dots not allowed in extension name: ' + name,
        name: name,

        assert std.findSubstr('-', version)  == []: 'Dashes not allowed in extension version: (' + name + ') ' + version,
        version: std.strReplace(version, '.', '_'),

        local NAME_VERSION = self.name + '-' + self.version,

        commit: commit,
        path: $['Environment'].Flatpak.Constant.EXTENSION_MOUNT_PATH + '/' + NAME_VERSION,
        flatpak: $['Environment'].Flatpak.Constant.EXTENSION_BASE_NAME + '.' + NAME_VERSION +
                 $['Environment'].Flatpak.Constant.EXTENSION_BRANCH,
      },

      // List of Project flatpak environment extensions. Path and link order matter.
      Extensions: [],
    }
  }
}
