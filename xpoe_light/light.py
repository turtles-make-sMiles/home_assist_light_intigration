"""Platform for light integration."""
from __future__ import annotations

import logging

#import awesomelights
import voluptuous as vol
import requests
import json



# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (ATTR_BRIGHTNESS, PLATFORM_SCHEMA,
                                            LightEntity)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_USERNAME, default='admin'): cv.string,
    vol.Optional(CONF_PASSWORD): cv.string,
    #vol.Optional(CONF_MAX_LEVEL, default=10): cv.int,
    #vol.Optional(CONF_FADE_TIME, default=1): cv.int,
})


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the XPOE Light platform."""
    # Assign configuration variables.
    # The configuration check takes care they are present.
    host = config[CONF_HOST]
    username = config[CONF_USERNAME]
    password = config.get(CONF_PASSWORD)
    #max_level = config.get(CONF_MAX_LEVEL)
    #fade_time = config.get(CONF_FADE_TIME)

    # Setup connection with devices/cloud
    _LOGGER.info('xpoe setup_platform() init')
    hub = awesomelights.Hub(host, username, password)
    

    # Verify that passed in configuration works
    if not hub.is_valid_login():
        _LOGGER.error("Could not connect to AwesomeLight hub")
        return

    # Add devices
    add_entities(AwesomeLight(light) for light in hub.lights())


class AwesomeLight(LightEntity):
    """Representation of an Awesome Light."""

    def __init__(self, light) -> None:
        """Initialize an AwesomeLight."""
        self._light = light
        self._name = light.name
        self._state = None
        self._brightness = None

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def brightness(self):
        """Return the brightness of the light.
        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return self._brightness

    @property
    def supported_features(self):
        """Flag supported features.
        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return 1 #SUPPORT_BRIGHTNESS  # or use 1 instead of the constant

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    def turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on.
        You can skip the brightness part if your light does not support
        brightness control.
        """
        self._light.brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        self._light.turn_on()

    def turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        self._light.turn_off()

    def update(self) -> None:
        """Fetch new state data for this light.
        This is the only method that should fetch new data for Home Assistant.
        """
        self._light.update()
        self._state = self._light.is_on()
        self._brightness = self._light.brightness


class XpoeLights(object):
    pass


class XPoe_Light(object):
    def __init__(self, host, chan_num, max_level=10,fade_time=1):
        _LOGGER.info('XpoeSwitch() init')
        self.name = 'Xpoe Channel {}'.format(chan_num)
        self.chan_num=chan_num
        self.brightness = max_level
        self.fade_time = fade_time
        self.host = host
        self.url = "http://{}:5000/api/level?sync=True".format(self.host)
        #self.url = "http://192.168.42.93:5000/api/level?sync=True"
    on = False
    def update(self):
        _LOGGER.info('update() called')
        # Not really sure when/why this is called
        # seen it called once, is_on() called often
    def is_on(self):
        _LOGGER.info('is_on() called')
        return self.on
    def turn_on(self):
        _LOGGER.info('turn_on() called XPoe_Light ON')
        
        payload = json.dumps({
        "payload": {
            "channels": [
            self.chan_num
            ],
            "target_level": self.brightness*100/255,
            "fade_time": self.fade_time
        }
        })
        headers = {
        'Content-Type': 'application/json'
        }

        response = requests.request("POST", self.url, headers=headers, data=payload)

        #print(response.text)
        self.on = True
    def turn_off(self):
        _LOGGER.info('turn_off() called XPoe_Light OFF')

        payload = json.dumps({
        "payload": {
            "channels": [
            self.chan_num
            ],
            "target_level": 0,
            "fade_time": self.fade_time
        }
        })
        headers = {
        'Content-Type': 'application/json'
        }

        response = requests.request("POST", self.url, headers=headers, data=payload)

        self.on = False

class XpoeSwitch(object):
    def __init__(self, host, username, password,max_level=10,fade_time=1,num_channels=8):
        _LOGGER.info('XpoeSwitch() init')
        self.host = host
        self.username = username
        self.password = password
        self.max_level=max_level
        self.fade_time = fade_time
        self.num_channels=num_channels
    def is_valid_login(self):
        return True
    def lights(self):
        # Fake discovery
        xpoe_light_list = []
        for x in range(self.num_channels):
            print(x)
            xpoe_light_list.append(XPoe_Light(self.host, x+1, self.max_level,self.fade_time))
        return xpoe_light_list

awesomelights = XpoeLights()
awesomelights.Hub = XpoeSwitch