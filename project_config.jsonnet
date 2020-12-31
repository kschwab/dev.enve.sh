local Project = import 'project.jsonnet';

{
  Project: Project {
    Environment+: {
      Flatpak+: {
        Extensions+: [
          Project.Environment.Flatpak.Extension('gcc', '4.8.5'),
        ],
      },
    },
  },
}
