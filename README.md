# pibooth_print_custom

Pibooth plugin to use a printer with ESC-OS (Thermic printer)



# Installation


You have to copy the file `pibooth_print_custom.py` in the directory of your plugins.

# Configuration

-------------
Plugin configuration
-------------

In your configuration file `.config/pibooth/pibooth.cfg` you have to configure all parameters below : 

Declaration of this plugin : 

    [GENERAL]
        
    # Path to custom plugin(s) not installed with pip (list of quoted paths accepted)
    plugins = /<Full Path>/pibooth_print_custom.py
note:: Edit the configuration by running the command ``pibooth --config`` or editing the `.config/pibooth/pibooth.cfg` file.

or if you have more than one plugin you have to make a table like that:

    [GENERAL]
        
    # Path to custom plugin(s) not installed with pip (list of quoted paths accepted)
    plugins = ('/<Full Path>/pibooth_ftp.py', '/<Full Path>/pibooth_print_custom.py')
note:: Edit the configuration by running the command ``pibooth --config`` or editing the `.config/pibooth/pibooth.cfg` file.



-------------
pibooth_print_custom Configuration
-------------

Here the new configuration options available in the `pibooth` configuration.
**The keys and their default values are automatically added to your configuration after first** `pibooth`_ **restart.**

    
    [ESC_POS]
    # Path to the ESC/POS printing script (default: /home/seb/print_raster.py)
    script_path = /home/seb/print_raster.py

    # Serial device for the thermal printer (default: /dev/ttyS0)
    serial_device = /dev/ttyS0

    # Target width in pixels for the printed image (default: 384)
    target_width = 384

    # Serial speed in baud (default: 9600)
    # Recommended values: 9600 (stable), 19200, 38400
    # Leave empty to use the script default
    baudrate = 9600

    # Boolean flags (True/False)
    # no_autorotate: Disable automatic portrait rotation (default: False)
    no_autorotate = False
    # pre_cancel: Flush/reset printer before printing (default: True)
    pre_cancel = True
    # invert: Invert black/white (default: True)
    invert = True
    # no_dither: Disable dithering (default: False)
    # If True, threshold will be applied; if False, threshold is ignored by the script
    no_dither = False

    # Numeric options (empty = disabled)
    # threshold: Used only if no_dither=True (default: 130)
    threshold = 130
    # contrast: Contrast adjustment before binarization (default: 1.3)
    contrast = 1.3
    # gamma: Gamma correction (default: disabled)
    gamma =
    # chunk: Serial write chunk size in bytes (default: 4096)
    chunk = 4096
    # line_sleep: Pause between raster bands in seconds (default: 0.02)
    line_sleep = 0.02
    # limit_lines: Limit number of printed lines (debug/paper save) (default: disabled)
    limit_lines =

    # Debug options (empty = disabled)
    # preview: Path to save 1-bit preview image (default: disabled)
    preview =
    # dry_run: Path to save ESC/POS stream without printing (default: disabled)
    dry_run =

note:: Edit the configuration by running the command ``pibooth --config`` or editing the `.config/pibooth/pibooth.cfg` file.




