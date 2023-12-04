# Features


Cordage can be used to manage experimental configurations and can aide in managing experimental outputs.


## Experimental Configuration

Cordage helps in providing a configuration to a main function. This set of features is the default and (at the moment) cannot be disabled.

### CLI and Config Reader

When calling `cordage.run` with a function, a command line interface is build.
This enables you to set the configurations specified in a config `dataclass` to be set via the command line or pass a configuration files which is automatically read into an respective config object.

### Series of Experiments / Multiruns

By specifying the `__series__` key in a passed config file, the experiment can be repeated multiple time with varying configuration.
`__series__` can either contain a list of changes to apply to the base configuration or a (nested dictionary) with mutliple lists (in this case each combination of values is executed once).


### Examples

The following will execute 3 repetitions:

``` json
{
    "__series__": [
        {"a": 1},
        {"a": 2},
        {"a": 3}
    ]
}
```

This second example will execute the experiment 4 times:

``` json
{
    "__series__": {
        "a": [1, 2],
        "b": [1, 2]
    }
}

```



## Output directory (optional)

Cordage creates an output directory for each experiment based on the configured pattern and stores
the 
If configured (see [below](#log_setup)), the log-files are automatically saved here.


## Log Setup (optional)


