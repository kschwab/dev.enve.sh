// The base name for Project flatpak environment extensions
local PROJECT_FLATPAK_EXTENSION_BASE_NAME = 'project.dev.environ.extension';

{
  // Project development environment types and specifications
  Environment: {

    // Specifications for the Project flatpak development environment
    Flatpak: {

      // Template function for Project flatpak environment extension objects
      Extension(name, version, commit=null): {
        flatpak: PROJECT_FLATPAK_EXTENSION_BASE_NAME + '.' + name + '-' + version,
        commit: commit
      },

      // List of Project flatpak environment extensions. Path and link order matter.
      Extensions: null,
    }
  }
}
