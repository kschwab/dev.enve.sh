local Enve = import 'enve.libsonnet';

{
  Enve: Enve {
    id+: Enve.NewId('Hello World Example', 'X.Y.Z'),
    extensions+: [
      Enve.NewExtension('Hello', remote_name='hello-repo',
        variables=[
          Enve.NewVariable('BIN', path_export=true)
        ]),
    ],
  },
}
