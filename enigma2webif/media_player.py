"""Support for Enigma2 media players."""
import logging
import requests
import xmltodict
import voluptuous as vol
from datetime import datetime

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_TVSHOW,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PAUSE,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_STOP,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    STATE_OFF,
    STATE_ON,
    STATE_PLAYING,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.config_validation import PLATFORM_SCHEMA

_LOGGER = logging.getLogger(__name__)

CONF_USE_CHANNEL_ICON = "use_channel_icon"
CONF_DEEP_STANDBY = "deep_standby"
CONF_MAC_ADDRESS = "mac_address"
CONF_SOURCE_BOUQUET = "source_bouquet"

DEFAULT_NAME = "Enigma2 Webinterface Media Player"
DEFAULT_PORT = 80
DEFAULT_SSL = False
DEFAULT_USE_CHANNEL_ICON = False
DEFAULT_USERNAME = "root"
DEFAULT_PASSWORD = "dreambox"
DEFAULT_MAC_ADDRESS = ""
DEFAULT_SOURCE_BOUQUET = ""

SUPPORTED_ENIGMA2 = (
    SUPPORT_VOLUME_SET
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_TURN_OFF
    | SUPPORT_VOLUME_STEP
    | SUPPORT_TURN_ON
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
        vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
        vol.Optional(
            CONF_USE_CHANNEL_ICON, default=DEFAULT_USE_CHANNEL_ICON
        ): cv.boolean,
        vol.Optional(CONF_MAC_ADDRESS, default=DEFAULT_MAC_ADDRESS): cv.string,
        vol.Optional(CONF_SOURCE_BOUQUET, default=DEFAULT_SOURCE_BOUQUET): cv.string,
    }
)

ATTR_MEDIA_ID = "media_id"
ATTR_MEDIA_CHANNEL = "media_channel"
ATTR_MEDIA_CURRENTLY_RECORDING = "media_currently_recording"
ATTR_MEDIA_DESCRIPTION = "media_description"
ATTR_MEDIA_END_TIME = "media_end_time"
ATTR_MEDIA_START_TIME = "media_start_time"

class CreateDevice:
    URL_ABOUT = "/web/about"
    URL_GET_CURRENT = "/web/getcurrent"
    URL_TOGGLE_VOLUME_MUTE = "/web/vol?set=mute"
    URL_SET_VOLUME = "/web/vol?set=set"

    # newstate - (optional) number; one of
    # 0: Toggle StandBy
    # 1: DeepStandBy
    # 2: Reboot
    # 3: Restart Enigma
    # 4: Wakeup
    # 5: Standby
    URL_POWERSTATE = "/web/powerstate"
    URL_POWERSTATE_CHANGE = URL_POWERSTATE + "?newstate="
    TOGGLE_STANDBY = "0"
    DEEP_STANDBY = "1"
    WAKEUP = "4"
    STANDBY = "5"

    # pylint: disable=too-many-arguments, disable=too-many-instance-attributes
    def __init__(self, host=None, port=None, username=None, password=None, is_https=False, prefer_picon=False, mac_address=None, turn_off_to_deep=False, source_bouquet=None, message_display_timeout=None):
        """
        Defines an enigma2 device.
        :param host: IP or hostname
        :param port: Webif port
        :param username: e2 user
        :param password: e2 user password
        :param is_https: use https or not
        :param prefer_picon: if yes, return picon instead of screen grab
        :param mac_address: if set, send WOL packet on power on.
        :param turn_off_to_deep: If True, send to deep standby on turn off
        :param source_bouquet: Which bouquet ref you want to load
        :param message_display_timeout: The display timeout for the notification
        """
        logging.basicConfig(level=logging.INFO)

        if not host:
            _LOGGER.error('Missing host!')
            raise Exception('Connection to WebIf failed, host configuration value missing.', None)

        _LOGGER.debug(f"Initialising new webif client for host: {host}")
        self.session = requests.Session()
        self.session.auth = (username, password)

        self.mac_address = mac_address
        self.turn_off_to_deep = turn_off_to_deep

        # Now build base url
        protocol = 'http' if not is_https else 'https'

        if port is not None:
            self._base = f"{protocol}://{host}:{port}"
        else:
            self._base = f"{protocol}://{host}"

        self.is_offline = False
        self.default_all()
        self.get_version()

    def log_response_errors(response):
        """
        Logs problems in a response
        """
        _LOGGER.error("status_code %s", response.status_code)
        if response.error:
            _LOGGER.error("error %s", response.error)

    def default_all(self):
        """Default all the props."""
        self.state = None
        self.volume = None
        self.in_standby = True
        self.muted = False
        self.status_info = {}

    def set_volume(self, new_volume):
        """
        Sets the volume to the new value
        :param new_volume: int from 0-100
        :return: True if successful, false if there was a problem
        """
        url = '%s%s%s' % (self._base, self.URL_SET_VOLUME, str(new_volume))
        _LOGGER.debug('url: %s', url)

        return self._check_reponse_result(self.session.get(url))

    def turn_on(self):
        """
        Take the box out of standby.
        """
        if self.is_offline:
            _LOGGER.debug('Box is offline, going to try wake on lan')
            self.wake_up()

        url = '{}{}{}'.format(self._base, self.URL_POWERSTATE_CHANGE, self.WAKEUP)
        _LOGGER.debug('Wakeup box from standby. url: %s', url)
        return self._check_reponse_result(self.session.get(url))

    # pylint: disable=import-outside-toplevel
    def wake_up(self):
        """Send WOL packet to the mac."""
        if self.mac_address:
            from wakeonlan import send_magic_packet
            send_magic_packet(self.mac_address)
            _LOGGER.debug("Sent WOL magic packet to %s", self.mac_address)
            return True

        _LOGGER.warning("Cannot wake up host as mac_address is not known.")
        return False

    def turn_off(self):
        """
        Put the box out into standby.
        if turn_off_to_deep is True, go to deep standby.
        """
        url = '{}{}{}'.format(self._base, self.URL_POWERSTATE_CHANGE, self.STANDBY)
        _LOGGER.debug('Going into standby. url: %s', url)

        return self._check_reponse_result(self.session.get(url))

    def mute_volume(self):
        """
        Send mute command
        """
        url = '%s%s' % (self._base, self.URL_TOGGLE_VOLUME_MUTE)
        _LOGGER.debug('url: %s', url)

        response = self.session.get(url)
        if response.status_code != 200:
            return False

        # Dont want to deal with ElementTree, return true
        return True

    @staticmethod
    def _check_reponse_result(response):
        """
        :param response:
        :return: Returns True if command success, else, False
        """

        if response.status_code != 200:
            log_response_errors(response)
            raise Exception('Connection to WebIf failed.')

        return True

    def update(self):
        """
        Refresh current state based
        """
        _LOGGER.debug("Update state")
        powerXml = self._call_api(f"{self._base}{self.URL_POWERSTATE}")
        self.in_standby = powerXml['e2powerstate']['e2instandby'] == 'true'

        if self.is_offline or self.in_standby:
            _LOGGER.debug(f"Fallback to default state values (offline {self.is_offline}, standby {self.in_standby})")
            self.default_all()
            return

        volumeXml = self._call_api(f"{self._base}{self.URL_SET_VOLUME}")
        volumeInfo = volumeXml['e2volume']
        #stateXml = self._call_api(f"{self._base}{self.URL_GET_CURRENT}")
        #volumeInfo = stateXml['e2currentserviceinformation']['e2volume']
        self.muted = volumeInfo['e2ismuted'] == 'True'
        self.volume = int(volumeInfo['e2current'])

        subserviceXml = self._call_api(f"{self._base}/web/subservices")
        serviceInfo = subserviceXml['e2servicelist']['e2service']
        self.status_info[ATTR_MEDIA_CHANNEL] = serviceInfo['e2servicename']
        serviceReference = serviceInfo['e2servicereference']

        #currEvent = stateXml['e2currentserviceinformation']['e2eventlist']['e2event'][0]
        #self.status_info[ATTR_MEDIA_CURRENTLY_RECORDING] = False
        #self.status_info[ATTR_MEDIA_DESCRIPTION] = currEvent['e2eventname']
        #self.status_info[ATTR_MEDIA_ID] = currEvent['e2eventservicereference']
        #self.status_info[ATTR_MEDIA_CHANNEL] = currEvent['e2eventservicename']
        #startTime = int(currEvent['e2eventstart'])
        #duration = int(currEvent['e2eventduration'])
        #self.status_info[ATTR_MEDIA_START_TIME] = datetime.fromtimestamp(startTime).strftime("%H:%M")
        #self.status_info[ATTR_MEDIA_END_TIME] = datetime.fromtimestamp(startTime + duration).strftime("%H:%M")

    def get_version(self):
        """
        Returns enigma2 webinterface version
        """
        url = f"{self._base}{self.URL_ABOUT}"
        result = self._call_api(url)

        if self.is_offline or not result:
            _LOGGER.warning(f"{self._base}{self.URL_ABOUT}: Cannot get version as box is unreachable.")
            return None

        version = result['e2abouts']['e2about']['e2webifversion']
        _LOGGER.info(f"{self._base}: Enigma2 Webinterface version %s", version)
        # Discover the mac, so we can WOL the box later if needed
        if not self.mac_address:
            ip_addr = result['e2abouts']['e2about']['e2lanip']
            self.mac_address = result['e2abouts']['e2about']['e2lanmac']
            _LOGGER.info('found %s mac_address: %s', ip_addr, self.mac_address)

        return version

    def _call_api(self, url):
        """Perform one api request operation."""

        try:
            response = self.session.get(url)
        except requests.exceptions.ConnectionError as err:
            self.is_offline = True
            _LOGGER.error(f"There was a connection error calling {url}"
                          f" Please check the network connection to the Enigma2"
                          f" box is ok and enable debug logging in "
                          f"Enigma2 if required. Error: {err}")
            return None

        _LOGGER.debug(f"Got {response.status_code} from: %s", url)
        if response.status_code not in [200]:
            error_msg = "Got {} from {}: {}".format(
                response.status_code, url, response.text)
            _LOGGER.error(error_msg)

            # If box is in deep standby, dont raise this
            # over and over.
            if not self.is_offline:
                message = f"{url} is unreachable."
                _LOGGER.warning(message)
                self.is_offline = True
            return None

        self.is_offline = False
        if response.status_code == 200:
            return xmltodict.parse(response.text)

        if response.status_code == 401:
            raise Exception(f"{url}: Failed to authenticate with WebIf. Check your username and password.")
        if response.status_code == 404:
            raise Exception(f"Got a 404 from {url}. Do you have the Enigma2 WebInterface plugin installed and enabled (check with your browser)?")

        _LOGGER.error("Invalid response from WebIf: %s", response)
        return None

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up of an enigma2 media player."""
    if discovery_info:
        # Discovery gives us the streaming service port (8001)
        # which is not useful as Webif never runs on that port.
        # So use the default port instead.
        config[CONF_PORT] = DEFAULT_PORT
        config[CONF_NAME] = discovery_info["hostname"]
        config[CONF_HOST] = discovery_info["host"]
        config[CONF_USERNAME] = DEFAULT_USERNAME
        config[CONF_PASSWORD] = DEFAULT_PASSWORD
        config[CONF_SSL] = DEFAULT_SSL
        config[CONF_USE_CHANNEL_ICON] = DEFAULT_USE_CHANNEL_ICON
        config[CONF_MAC_ADDRESS] = DEFAULT_MAC_ADDRESS
        config[CONF_DEEP_STANDBY] = DEFAULT_DEEP_STANDBY
        config[CONF_SOURCE_BOUQUET] = DEFAULT_SOURCE_BOUQUET

    device = CreateDevice(
        host=config[CONF_HOST],
        port=config.get(CONF_PORT),
        username=config.get(CONF_USERNAME),
        password=config.get(CONF_PASSWORD),
        is_https=config[CONF_SSL],
        prefer_picon=config.get(CONF_USE_CHANNEL_ICON),
        mac_address=config.get(CONF_MAC_ADDRESS),
        turn_off_to_deep=config.get(CONF_DEEP_STANDBY),
        source_bouquet=config.get(CONF_SOURCE_BOUQUET),
    )

    add_devices([Enigma2Device(config[CONF_NAME], device)], True)


class Enigma2Device(MediaPlayerEntity):
    """Representation of an Enigma2 box."""

    def __init__(self, name, device):
        """Initialize the Enigma2 device."""
        self._name = name
        self.e2_box = device

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID for this entity."""
        return self.e2_box.mac_address

    @property
    def state(self):
        """Return the state of the device."""
        return STATE_OFF if self.e2_box.in_standby else STATE_ON

    @property
    def available(self):
        """Return True if the device is available."""
        return not self.e2_box.is_offline

    @property
    def supported_features(self):
        """Flag of media commands that are supported."""
        return SUPPORTED_ENIGMA2

    def turn_off(self):
        """Turn off media player."""
        self.e2_box.turn_off()

    def turn_on(self):
        """Turn the media player on."""
        self.e2_box.turn_on()

    @property
    def media_title(self):
        """Title of current playing media."""
        return self.e2_box.status_info[ATTR_MEDIA_CHANNEL]
        #return self.e2_box.status_info[ATTR_MEDIA_CHANNEL] + ": " + self.e2_box.status_info[ATTR_MEDIA_DESCRIPTION]

    @property
    def media_channel(self):
        """Channel of current playing media."""
        return self.e2_box.status_info[ATTR_MEDIA_CHANNEL]

    @property
    def media_content_id(self):
        """Service Ref of current playing media."""
        return self.e2_box.status_info[ATTR_MEDIA_CHANNEL]
        #return self.e2_box.status_info[ATTR_MEDIA_ID]

    @property
    def media_content_type(self):
        """Type of video currently playing."""
        return MEDIA_TYPE_TVSHOW

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self.e2_box.muted

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        self.e2_box.set_volume(int(volume * 100))

    def volume_up(self):
        """Volume up the media player."""
        self.e2_box.set_volume(self.e2_box.volume + 5)

    def volume_down(self):
        """Volume down media player."""
        self.e2_box.set_volume(self.e2_box.volume - 5)

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self.e2_box.volume / 100

    def mute_volume(self, mute):
        """Mute or unmute."""
        self.e2_box.mute_volume()

    def update(self):
        """Update state of the media_player."""
        self.e2_box.update()
