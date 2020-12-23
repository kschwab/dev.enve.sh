local Project = import 'project.jsonnet';

{
  Project+: {
    Environment: {
      Flatpak: {
        Extensions: [
          Project.Environment.Flatpak.Extension('name', 'version'),
          Project.Environment.Flatpak.Extension('name', 'version', 'commit'),
        ]
      }
    }
  }
}
