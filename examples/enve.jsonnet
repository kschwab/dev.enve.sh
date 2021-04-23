local Enve = import 'enve.libsonnet';

{
  Enve: Enve {
    id+: Enve.NewId('Hello World', 'X.Y.Z'),
    extensions+: [
      Enve.NewExtension('Hello_World',
        variables=[
          Enve.NewVariable('BIN', path_export=true)
        ]),
    ],
  },
}
