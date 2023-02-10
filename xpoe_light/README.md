# XPOE Lights

This integration shows how you would go ahead and integrate a xpoe light into Home Assistant.

### Installation

Copy xpoe_light folder to `<config_dir>/custom_components/xpoe_light/`.

Add the following entry in your `configuration.yaml`:

```yaml
light:
  - platform: xpoe_light
    host:  "yourxpoehost.local"
    username: "usernamefromconfig"
    password:  "passwordfromconfig"
```
