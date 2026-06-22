import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class RecordingInfo:
    def __init__(self, file_name: str, file_length: str, start_time: str, end_time: str, channel: str, type_: str, subtype: str):
        self.fileName = file_name
        
        if file_length.isdigit():
            self.fileLength = int(file_length)
        else:
            logger.warning("Invalid value for fileLength: '%s', defaulting to 0", file_length)
            self.fileLength = 0
            
        self.startTime = start_time
        self.endTime = end_time
        
        if channel.isdigit():
            self.channel = int(channel)
        else:
            logger.warning("Invalid value for channel: '%s', defaulting to 0", channel)
            self.channel = 0
            
        if type_.isdigit():
            self.type = int(type_)
        else:
            logger.warning("Invalid value for type_: '%s', defaulting to 0", type_)
            self.type = 0
            
        if subtype.isdigit():
            self.subtype = int(subtype)
        else:
            logger.warning("Invalid value for subtype: '%s', defaulting to 0", subtype)
            self.subtype = 0


class StorageDiskInfo:
    def __init__(self, name: str, total_bytes: str, free_bytes: str, used_bytes: str, usage: str, state: str, health: str, temperature: str):
        self.name = name
        
        if total_bytes.isdigit():
            self.totalBytes = int(total_bytes)
        else:
            logger.warning("Invalid value for total_bytes: '%s', defaulting to 0", total_bytes)
            self.totalBytes = 0
            
        if free_bytes.isdigit():
            self.freeBytes = int(free_bytes)
        else:
            logger.warning("Invalid value for free_bytes: '%s', defaulting to 0", free_bytes)
            self.freeBytes = 0
            
        if used_bytes.isdigit():
            self.usedBytes = int(used_bytes)
        else:
            logger.warning("Invalid value for used_bytes: '%s', defaulting to 0", used_bytes)
            self.usedBytes = 0
            
        if usage.isdigit():
            self.usagePercent = int(usage)
        else:
            logger.warning("Invalid value for usage: '%s', defaulting to 0", usage)
            self.usagePercent = 0
            
        self.state = state
        self.health = health
        self.temperature = temperature


class ChannelInfo:
    def __init__(self, index: str, name: str, online: bool):
        if index.isdigit():
            self.index = int(index)
        else:
            logger.warning("Invalid value for index: '%s', defaulting to 0", index)
            self.index = 0
        self.name = name
        self.online = online
