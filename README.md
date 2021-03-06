# homeassistant-enigma2webif
[Home Assistant](https://www.home-assistant.io/) enigma2 integration for boxes with the [WebInterface](https://dream.reichholf.net/wiki/Enigma2:WebInterface). For boxes with the [OpenWebIf](https://www.home-assistant.io/integrations/enigma2/), the integration is delivered with Home Assistant Core.

Copied, pasted, and adapted from [Homeassistant enigma2 OpenWebIf](https://github.com/home-assistant/core/tree/dev/homeassistant/components/enigma2) als well as [openwebifpy](https://github.com/fbradyirl/openwebifpy).

# Current state
## Works
- Standby toggle, wake-on-lan if offline (however, it will take some time for your box to startup)
- Volume controls
- Display of current TV channel and event.
- Configuration in [configuration.yaml](https://www.home-assistant.io/docs/configuration/)
## Works but...
- State changes are polled every 10s from the box. If you e.g. modify the volume with your IR remote, it takes up to 10s to reflect the new volume in Home Assistant.
- The API used to poll the state is `/web/getcurrent`, which takes quite long (4-8sec on a DM800) and therefore triggers the spinner and freeze the enigma2 UI.
- You will probably need things like SSH, SCP, chown, chmod, or vi/nano to get this to work. If you are not familiar with configuring Home Assistant and are not willing to find your way through the [Home Assistant docs](https://www.home-assistant.io/docs/configuration/), this integration is not for you ;-)
## Not yet
- Everything else (other media player features, GUI configuration, test coverage, ...)

# Installation
1. Copy the `enigma2webif` folder including its three files to your Home Assistant `/config/custom_compontents/` folder. Have a look [here](https://www.home-assistant.io/docs/configuration/) for more information about Home Assistant configuration.
2. Ensure the copied folder and files have correct file permissions, such that Home Assistant Core will be able to read them and write the python cache files inside the `enigma2webif` folder.

# Configuration
1. Configure your box(es) in Home Assistant Core `configuration.yaml`:
```
# Example configuration.yaml entry
media_player:
  - platform: enigma2webif
    host: IP_ADDRESS
```
Other configuration options:
| Option | Usage |
|--------|-------|
| ssl | Set to True to use HTTPS, False (default) for HTTP. |
| port | The TCP port to use. Defaults to `None`. |
| username | The username if Enigma2 WebInterface is configured with authentication. |
| password | The password if Enigma2 WebInterface is configured with authentication. |
| name | Default name of the created Home Assistant entity. |
| mac_address | Declare MAC address for wake-on-lan. The MAC address is read from the WebInterface API. Only useful, if there is no other way to wakeup an offline box. |
2. Restart Home Assistant Core
3. Find a new entity of type "media player" with limited capabilities in the list of Home Assistant entities.

# Support
This Home Assistant integration comes without support.

# Debugging
1. Set the log level to `debug` for the `enigma2webif` media player component. Example configuration.yaml entry:
```
# Example configuration.yaml entry
logger:
  default: warning
  logs:
    custom_components.enigma2webif.media_player: debug
```
2. Have a look at `homeassistant.log`in your preferred way.

# Enigma2 WebInterface Docs
- [WebInterface](https://dream.reichholf.net/wiki/Enigma2:WebInterface)
- [API Spec](https://dream.reichholf.net/e2web/)


