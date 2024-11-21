# Better Caution Bot

This project is primarily aimed to provide a better experience for Cautions/Safety Cars in iRacing during Road races. It is a standalone app meant to be run by an Admin during a hosted or league session. It uses [Kutu's pyirsdk](https://github.com/kutu/pyirsdk) to read the iRacing API data, and [Streamlit](https://streamlit.io) to provide a UI for the Admin to control the Cautions.

While the original intention was to automate Cautions for The Beer League, this bot has been designed to be flexible for other types of orchestrated events, both random and planned, with configurable event sequences when those events occur.

## Features
- **Random Caution Bot** - triggers an iRacing caution at a random time within a given time window.
    - When the caution is triggered, the bot will first close pit lane, and wait for any cars already on pit lane to exit before throwing the caution. This is intended to prevent the 'Phantom EOL' bug, where cars that are on pit lane when a caution is thrown are told to let cars by, but those cars are not told to pass them.
- **Random Code 60 Bot** - triggers a fully custom Code 60-like event at a random time within a given time window, providing instructions to drivers via text chat.
    - Originally designed for longer tracks where the minimum 3 laps of pacing would take a long time. This event instructs the leader to slow down after crossing the start/finish line, and all cars to form up behind them in a frozen order. Cars that overtake or are overtaken are instructed to return to the proper order. It can instruct cars to line up double file, or restart directly from the single file order. When restarting, it monitors the leader's speed and announces the green flag when they accelerate.
- **Sprint Race DQ** - Waits for a specific moment in the race, and issues a configurable penalty to the specified cars. Typically used to ensure drivers start Feature races from the back of the field despite their finishing position in the Sprint/Heat races.
- **Beer Goggles** - A very simple wrapper for exposing all the data provided by the API. Meant to be used for debugging and testing the bot.


## Installation
1. Install Python 3.12 or later from [python.org](https://www.python.org/downloads/)
2. Clone this repository to your computer or download the ZIP file and extract it.
3. Run the 'install.bat' file to create a python virtual environment and install the required Python packages in it.
    - Windows is likely to complain about the unknown publisher of the 'install.bat' file. Always use caution when running scripts from the internet. If you are uncomfortable running the script, you can open it in a text editor to see the commands it runs and run them manually in a terminal window.
4. Run the 'run.bat' file to start the Streamlit server and open the app in your default web browser.
    - Windows will also complain about the unknown publisher of the 'run.bat' file. You can open it in a text editor to see the commands it runs and run them manually in a terminal window.
    - The first time you start Streamlit, you may be prompted to enter an email address for sharing usage data with Streamlit. This is optional and can be skipped by pressing the 'Enter' key in the terminal window.

## Planned Features
- **Multiclass Restarts** to help with class separation during restarts.
- **Auto Black-Flag Clearing** to run `!clearall` on a loop for no-rules races or practice sessions
- **Incident Limit Enforcement** to issue penalties to drivers who exceed a configurable number of incidents in a session.

## Contributing
If you would like to contribute to this project, please fork the repository and submit a pull request with your changes. If you have any questions or need help with the code, please open an issue on the repository and I will do my best to help you.

## License
This project is licensed under the GNU General Public License v3.0. You are free to use, modify, and distribute this code as long as you adhere to the terms of the license.