# slack-export
A python slack exporter

The included script 'slack_export.py' works with a provided token to export Channels, Private Channels, Direct Messages and Multi Person Messages.

This script finds all channels, private channels and direct messages that your user participates in, downloads the complete history for those converations and writes each conversation out to seperate json files.

This user centric history gathering is nice because the official slack data exporter only exports public channels.

There may be limitations on what you can export based on the paid status of your slack account.

This use of the API is blessed by Slack : https://get.slack.help/hc/en-us/articles/204897248
" If you want to export the contents of your own private groups and direct messages
please see our API documentation."

One way to get your token is to obtain it here:
https://api.slack.com/custom-integrations/legacy-tokens

dependencies:
```
   pip install slacker #https://github.com/os/slacker
```

usage examples
```
   python slack_export.py --token=xoxs-123123-123123-4123-0a141234
   python slack_export.py --token=123token --dryRun
   python slack_export.py --token=123token --skipDirectMessages
   python slack_export.py --token=123token --skipDirectMessages --skipPrivateChannels -zip slack_export_1
   python slack_export.py --token=123token --onlySpecifiedPrivateChannels General Random --dryRun
```
This script is provided in an as-is state and I guarantee no updates or quality of service at this time.

# Recommended related libraries

This is designed to function with 'slack-export-viewer'.
  ```
  pip install slack-export-viewer
  ```

Then you can execute the viewer as documented
```
slack-export-viewer -z zipArchive.zip
```

# Enjoy the tool? Want to encourage me to fix your requested issue? :D

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=B8HSSU3SDLBRC)
