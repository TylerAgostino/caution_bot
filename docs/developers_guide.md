# Developer's Guide
## Introduction
This document provides a guide for developers who want to contribute to the project. It includes a basic overview of the classes and functions in the project, as well as some guidelines for contributing to the project.

## Events
The project is designed around the concept of Events. Events have a time where they are scheduled to occur (based on the session time) and an event sequence that is executed when the event occurs.

### BaseEvent
The `BaseEvent` class is the base class for all events. It provides a common interface for all events, including exposing the sdk, logger, and various functions that are not specific to any one event. It leaves the event sequence to be implemented by the derived classes.

### RandomTimedEvent
An extension on the BaseEvent that takes the start and end of a time window, and randomly chooses a time within that window to trigger the event. This is used for the Random Caution and Random Code 69 events.

### RandomCautionEvent
An event that triggers a caution at a random time within a given time window. It waits for cars on pit lane to exit before throwing the caution to prevent the 'Phantom EOL' bug.

### RandomCode69Event
An event that triggers a fully custom Code 60-like event at a random time within a given time window. It provides instructions to drivers via text chat.

## Streamlit UI
The Streamlit UI is the primary interface for the Admin to control the Cautions. It is built using the Streamlit library, which provides a simple way to create web apps using Python.

Most events currently have their own UI page, however it's likely that some events will be shared on multiple pages in the future.

## SubprocessManager
Because the Streamlit UI occupies the main python thread, the UI will stop updating and become greyed out when other code is running on the main thread. This might be OK in some situations, but for most subclasses of the BaseEvent class, it would cause the UI to be unresponsive for most of the race. Instead, we use the SubprocessManager to run the event sequences in separate threads, allowing the UI to continue updating and responding to user input. The SubprocessManager also provides a way to stop the event sequences if the Admin decides to cancel the event, and uses threading.Event objects for communication between the main thread and the event sequences, as well among the event sequences themselves. These are used to signal that events should cancel (a check is done after the self.sleep() method of the BaseEvent class), as well as signalling 'Busy' when an event is already running, to prevent multiple events from running at the same time.