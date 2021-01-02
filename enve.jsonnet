local Enve = import 'enve.libsonnet';

{
  Enve: Enve {
    Flatpak+: {
      Extensions+: [
        Enve.Flatpak.Extension('gcc-4_8_5', 'gcc'),
        // Project.Environment.Flatpak.Extension('dummy-4_8_5'),
      ],
    },
  },
}
