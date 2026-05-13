# Better Caution Bot

This project is primarily aimed to provide a better experience for Cautions/Safety Cars in iRacing during Road races. It is a standalone desktop app meant to be run by an Admin during a hosted or league session. It uses [Kutu's pyirsdk](https://github.com/kutu/pyirsdk) to read the iRacing API data, and [Flet](https://flet.dev) to provide a native desktop UI for the Admin to control the events.

While the original intention was to automate Cautions for The Beer League, this bot has been designed to be flexible for other types of orchestrated events, both random and planned, with configurable event sequences when those events occur.

## Features
- **Random Caution Bot** - triggers an iRacing caution at a random time within a given time window.
    - When the caution is triggered, the bot will first close pit lane, and wait for any cars already on pit lane to exit before throwing the caution. This is intended to prevent the 'Phantom EOL' bug, where cars that are on pit lane when a caution is thrown are told to let cars by, but those cars are not told to pass them.
- **Random Code 69 Bot** - triggers a fully custom Code 60-like event at a random time within a given time window, providing instructions to drivers via text chat.
    - Originally designed for longer tracks where the minimum 3 laps of pacing would take a long time. This event instructs the leader to slow down after crossing the start/finish line, and all cars to form up behind them in a frozen order. Cars that overtake or are overtaken are instructed to return to the proper order. It can instruct cars to line up double file, or restart directly from the single file order. When restarting, it monitors the leader's speed and announces the green flag when they accelerate.
    - Supports Class Separation for multiclass races, automatic wave-arounds for lapped cars as well as cars 'trapped' a lap down (overall leader between them and their leader while on the same lap as their leader)
    - Supports fully scripted class separation, multilane restart, and green flag based on a predetermined pacing distance before each event
- **Multi-Driver Incident Caution** - throws a caution when a configurable number of drivers earn a 4x incident within a rolling time window. The drivers threshold can optionally auto-increase after each caution to avoid over-yellowing as a race gets more ragged.
- **Sprint Race DQ** - Waits for a specific moment in the race, and issues a configurable penalty to the specified cars. Typically used to ensure drivers start Feature races from the back of the field despite their finishing position in the Sprint/Heat races.
- **Clear All Black Flags** - Every few seconds, if any driver is being shown a black flag, the bot will send the `!clearall` command to clear all black flags.
- **Discord Integration** - Provides audio cues for Code 69 and Caution events. Bring your own Discord bot token and channel ID.
- **Scheduled Messages** - Allows the Admin to schedule messages to be sent to the iRacing chat at specific times.
- **Incident Limit Enforcement** - Give drivers a penalty after X incidents, then every Y until Z incidents. The incidents and penalties are configurable.
- **Car Contact Limit** - Give drivers a penalty after a certain number of 4x incidents. Also quacks.
- **Gap to Leader Penalty** - Monitors each car's gap to the race leader. Issues a warning at 75% of the threshold, then a configurable penalty once a car falls beyond the maximum allowed gap. Cars that receive a penalty are considered out of the race and won't be penalized again.
- **OBS Overlay** - Serves transparent HTML overlays over a local HTTP server for use as OBS browser sources. Overlays update in real time via SSE and include a Race Control message banner and the F1 qualifying timing tower.
- **Beer Goggles** - A very simple wrapper for exposing all the data provided by the API. Meant to be used for debugging and testing the bot.
- **F1-style Qualifying** - Uses text chat to organize a knockout-style qualifying. Use this with iRacing's custom grid to simulate an F1 style qualifying session. Configurable number of rounds and number of cars advancing from each round. UI displays a timing board that can be screen-shared in Discord, but position updates are also sent directly to drivers via in-game chat.


## Installation

### Option 1: Pre-built Executable (Recommended)
1. Download the latest `BetterCautionBot.zip` from the [Releases](../../releases) page.
2. Extract the ZIP file to a folder of your choice.
3. Run `BetterCautionBot.exe` to launch the app.

### Option 2: Run from Source
1. Install Python 3.13 or later from [python.org](https://www.python.org/downloads/).
2. Clone this repository or download and extract the ZIP file.
3. Open a terminal in the project folder and create a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Launch the app:
   ```
   python BetterCautionBot.py
   ```

## Contributing
If you would like to contribute to this project, please fork the repository and submit a pull request with your changes. If you have any questions or need help with the code, please open an issue on the repository and I will do my best to help you.

## License
This project is licensed under the GNU General Public License v3.0. You are free to use, modify, and distribute this code as long as you adhere to the terms of the license.