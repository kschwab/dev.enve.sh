local Enve = import 'enve.libsonnet';

{
  Enve: Enve {
    id+: Enve.NewId('Project', 'X.Y.Z'),
    extensions+: [
      Enve.NewExtension('gcc-4_8_5', 'gcc',
        variables=[
          Enve.NewVariable('BIN', 'bin', path_export=true)
        ]),
      // Enve.NewExtension('dummy-4_8_5'),
    ],
    // variables+: [
    //   Enve.NewVariable('PATH', ['bin'], auto_load=true),
    // ],
  },
}
