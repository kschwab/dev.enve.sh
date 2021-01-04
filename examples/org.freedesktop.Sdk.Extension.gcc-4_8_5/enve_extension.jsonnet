local Enve = import 'enve.libsonnet';

{
  variables: [
    // Will generate ENVE_ALIAS_PATH. Auto load will prepend parameters to PATH using delimeter.
    Enve.NewVariable('PATH', ['bin'], auto_load=true),
  ],
}
