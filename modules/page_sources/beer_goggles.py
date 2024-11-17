import streamlit as st
from streamlit_autorefresh import st_autorefresh
from modules.events.base_event import BaseEvent
import pandas as pd

logger = st.session_state.logger

def connect():
    st.session_state.goggle_event = BaseEvent()

def disconnect():
    if 'goggle_event' in st.session_state:
        del st.session_state['goggle_event']

def ui():
    st.header("Beer Goggles SDK Viewer")
    col1, col2, _ = st.columns([1, 1, 3])
    col1.button('Connect', on_click=connect)
    col2.button('Disconnect', on_click=disconnect)
    if 'goggle_event' in st.session_state:
        global_field_sections = {
            'Session': ['SessionTime', 'SessionTick', 'SessionNum', 'SessionState', 'SessionUniqueID', 'SessionFlags',
                        'SessionTimeRemain', 'SessionLapsRemain', 'SessionLapsRemainEx', 'SessionTimeTotal',
                        'SessionLapsTotal', 'SessionJokerLapsRemain', 'SessionLapsRemain', 'SessionLapsRemainEx',
                        'SessionTimeTotal', 'SessionLapsTotal', 'SessionJokerLapsRemain', 'SessionOnJokerLap',
                        'SessionTimeOfDay', 'PaceMode', 'TrackTemp', 'TrackTempCrew', 'AirTemp', 'TrackWetness', 'Skies',
                        'AirDensity', 'AirPressure', 'WindVel', 'WindDir', 'RelativeHumidity', 'FogLevel', 'Precipitation',
                        'SolarAltitude', 'SolarAzimuth', 'WeatherDeclaredWet', ],
            'Player Car': ['PlayerCarPosition', 'PlayerCarClassPosition', 'PlayerCarClass', 'PlayerTrackSurface',
                           'PlayerTrackSurfaceMaterial', 'PlayerCarIdx', 'PlayerCarTeamIncidentCount',
                           'PlayerCarMyIncidentCount', 'PlayerCarDriverIncidentCount','PlayerCarWeightPenalty',
                           'PlayerCarPowerAdjust', 'PlayerCarDryTireSetLimit', 'PlayerCarTowTime',
                           'PlayerCarInPitStall', 'PlayerCarPitSvStatus', 'PlayerTireCompound', 'PlayerFastRepairsUsed',
                           'OnPitRoad', 'SteeringWheelAngle', 'Throttle', 'Brake', 'Clutch', 'Gear', 'RPM',
                           'PlayerCarSLFirstRPM', 'PlayerCarSLShiftRPM', 'PlayerCarSLLastRPM', 'PlayerCarSLBlinkRPM',
                           'Lap', 'LapCompleted', 'LapDist', 'LapDistPct', 'RaceLaps', 'CarDistAhead', 'CarDistBehind',
                           'LapBestLap', 'LapBestLapTime', 'LapLastLapTime', 'LapCurrentLapTime', 'LapLasNLapSeq',
                           'LapLastNLapTime', 'LapBestNLapLap', 'LapBestNLapTime', 'LapDeltaToBestLap', 'LapDeltaToBestLap_DD',
                           'LapDeltaToBestLap_OK', 'LapDeltaToOptimalLap', 'LapDeltaToOptimalLap_DD', 'LapDeltaToOptimalLap_OK',
                           'LapDeltaToSessionBestLap', 'LapDeltaToSessionBestLap_DD', 'LapDeltaToSessionBestLap_OK',
                           'LapDeltaToSessionOptimalLap', 'LapDeltaToSessionOptimalLap_DD', 'LapDeltaToSessionOptimalLap_OK',
                           'LapDeltaToSessionLastlLap', 'LapDeltaToSessionLastlLap_DD', 'LapDeltaToSessionLastlLap_OK', 'Speed',
                           'Yaw', 'YawNorth', 'Pitch', 'Roll', 'EnterExitReset', 'DCLapStatus', 'DCDriversSoFar', 'CarLeftRight', 'PitsOpen',
                           'IsOnTrackCar', 'IsInGarage', 'SteeringWheelAngleMax', 'ShiftPowerPct', 'ShiftGrindRPM',
                           'ThrottleRaw', 'BrakeRaw', 'ClutchRaw', 'HandbrakeRaw', 'BrakeABSactive', 'EngineWarnings', 'FuelLevelPct',
                           'P2P_Status', 'P2P_Count', 'SteeringWheelPctTorque', 'SteeringWheelPctTorqueSign',
                           'SteeringWheelPctTorqueSignStops', 'SteeringWheelPctIntensity', 'SteeringWheelPctSmoothing',
                           'SteeringWheelPctDamper', 'SteeringWheelLimiter', 'SteeringWheelMaxForceNm', 'SteeringWheelPeakForceNm',
                           'SteeringWheelUseLinear', 'ShiftIndicatorPct', 'IsGarageVisible', 'SteeringWheelTorque_ST',
                           'SteeringWheelTorque', 'VelocityZ_ST', 'VelocityY_ST','VelocityX_ST', 'VelocityZ', 'VelocityY', 'VelocityX',
                           'YawRate_ST', 'PitchRate_ST', 'RollRate_ST', 'YawRate', 'PitchRate', 'RollRate', 'VertAccel_ST', 'LatAccel_ST',
                           'LongAccel_ST', 'VertAccel', 'LatAccel', 'LongAccel', 'dcStarter', 'dcTearOffVisor', 'dcBrakeBias',
                           'LFshockDefl_ST', 'LFshockVel', 'LFshockVel_ST', 'RFshockDefl', 'RFshockDefl_ST', 'RFshockVel', 'RFshockVel_ST'],
            'Telemetry': ['RFcoldPressure', 'RFtempCL', 'RFtempCM', 'RFtempCR', 'RFwearL', 'RFwearM', 'RFwearR', 'LFcoldPressure',
                          'LFtempCL', 'LFtempCM', 'LFtempCR', 'LFwearL', 'LFwearM', 'LFwearR', 'FuelUsePerHour', 'Voltage', 'WaterTemp',
                          'RRcoldPressure', 'RRtempCL', 'RRtempCM', 'RRtempCR', 'RRwearL', 'RRwearM', 'RRwearR', 'LRcoldPressure',
                          'LRtempCL', 'LRtempCM', 'LRtempCR', 'LRwearL', 'LRwearM', 'LRwearR', 'LRshockDefl', 'LRshockDefl_ST',
                          'LRshockVel', 'LRshockVel_ST', 'RRshockDefl', 'RRshockDefl_ST', 'RRshockVel', 'RRshockVel_ST', 'LFshockDefl',
                          ],
            'Pits': ['PitRepairLeft', 'PitOptRepairLeft', 'PitstopActive', 'FastRepairUsed', 'FastRepairAvailable', 'LFTiresUsed',
                     'RFTiresUsed', 'LRTiresUsed', 'RRTiresUsed', 'LeftTireSetsUsed', 'RightTireSetsUsed', 'FrontTireSetsUsed',
                     'RearTireSetsUsed', 'TireSetsUsed', 'LFTiresAvailable', 'RFTiresAvailable', 'LRTiresAvailable',
                     'RRTiresAvailable', 'LeftTireSetsAvailable', 'RightTireSetsAvailable', 'FrontTireSetsAvailable',
                     'RearTireSetsAvailable', 'TireSetsAvailable', 'PitSvFlags', 'PitSvLFP', 'PitSvRFP', 'PitSvLRP', 'PitSvRRP', 'PitSvFuel', 'PitSvTireCompound',
                     'dpRFTireChange', 'dpLFTireChange', 'dpRRTireChange', 'dpLRTireChange', 'dpFuelFill', 'dpFuelAddKg', 'dpFastRepair',
                     'dpLFTireColdPress', 'dpRFTireColdPress', 'dpLRTireColdPress', 'dpRRTireColdPress',
                     'WaterLevel', 'FuelPress', 'OilTemp', 'OilPress', 'OilLevel', 'ManifoldPress', 'FuelLevel', 'Engine0_RPM',

                     ],
            'Audio': ['RadioTransmitCarIdx', 'RadioTransmitRadioIdx', 'RadioTransmitFrequencyIdx',
                      'TireLF_RumblePitch', 'TireRF_RumblePitch', 'TireLR_RumblePitch', 'TireRR_RumblePitch', ],
            'Player Misc': ['PushToTalk', 'PushToPass', 'ManualBoost', 'ManualNoBoost', 'IsOnTrack'],
            'Player Settings': ['DisplayUnits', 'DriverMarker', ],
            'Performance': ['IsDiskLoggingEnabled', 'IsDiskLoggingActive', 'FrameRate', 'CpuUsageFG', 'GpuUsage',
                            'ChanAvgLatency', 'ChanLatency','ChanQuality', 'ChanPartnerQuality', 'CpuUsageBG',
                            'ChanClockSkew', 'MemPageFaultSec', 'MemSoftPageFaultSec', 'VidCapEnabled', 'VidCapActive', ],
            'Replay': ['IsReplayPlaying', 'ReplayFrameNum', 'ReplayFrameNumEnd', 'OkToReloadTextures', 'LoadNumTextures',
                       'CamCarIdx', 'CamCameraNumber', 'CamGroupNumber', 'CamCameraState', 'ReplayPlaySpeed',
                       'ReplayPlaySlowMotion', 'ReplaySessionTime', 'ReplaySessionNum',  ]

        }

        field_df_cols =  ['CarIdxLap', 'CarIdxLapCompleted', 'CarIdxLapDistPct', 'CarIdxTrackSurface',
                  'CarIdxTrackSurfaceMaterial', 'CarIdxOnPitRoad', 'CarIdxPosition', 'CarIdxClassPosition',
                  'CarIdxClass', 'CarIdxF2Time', 'CarIdxEstTime', 'CarIdxLastLapTime', 'CarIdxBestLapTime',
                  'CarIdxBestLapNum', 'CarIdxTireCompound', 'CarIdxQualTireCompound',
                  'CarIdxQualTireCompoundLocked', 'CarIdxFastRepairsUsed', 'CarIdxSessionFlags','CarIdxPaceLine',
                  'CarIdxPaceRow', 'CarIdxPaceFlags', 'CarIdxSteer', 'CarIdxRPM', 'CarIdxGear', 'CarIdxP2P_Status', 'CarIdxP2P_Count']

        with st.expander("Live Telemetry"):
            tabs = st.tabs(global_field_sections.keys())
            for i, (section, fields) in enumerate(global_field_sections.items()):
                with tabs[i]:
                    # df = pd.DataFrame()
                    for field in fields:
                        value = st.session_state.goggle_event.sdk[field]
                        if isinstance(value, list):
                            st.write(f'{field}: {value}')
                        else:
                            st.metric(field, value)

        session_info = {
            'DriverInfo': {k: v for k,v in st.session_state.goggle_event.sdk['DriverInfo'].items() if k != 'Drivers'},
            'Drivers': st.session_state.goggle_event.sdk['DriverInfo']['Drivers'],
            'QualifyResultsInfo': st.session_state.goggle_event.sdk['QualifyResultsInfo']['Results'],
            'SplitTimeInfo': st.session_state.goggle_event.sdk['SplitTimeInfo']['Sectors'],
            'WeekendInfo': {k: v for k,v in st.session_state.goggle_event.sdk['WeekendInfo'].items() if k != 'WeekendOptions' and k != 'TelemetryOptions'},
            'WeekendOptions': st.session_state.goggle_event.sdk['WeekendInfo']['WeekendOptions'],
        }
        with st.expander("Static Info"):
            tabs = st.tabs(session_info.keys())
            for i, (section, fields) in enumerate(session_info.items()):
                with tabs[i]:
                    if isinstance(fields, list):
                        st.dataframe(fields)
                    else:
                        for field, value in fields.items():
                            st.metric(field, value)
            # for key, value in session_info.items():
            #     st.subheader(key)
            #     st.dataframe(value)

        car_idx_obj = {str(header).replace('CarIdx',''): st.session_state.goggle_event.sdk[header] for header in field_df_cols}
        car_idx_df = pd.DataFrame(car_idx_obj)

        st.write('---')
        st.subheader('Per Car Data')
        st.dataframe(car_idx_df)
        st_autorefresh()


beer_goggles = st.Page(ui, title='Beer Goggles', url_path='beer_goggles', icon="🔍")