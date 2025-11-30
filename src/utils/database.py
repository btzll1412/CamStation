"""
Database management for CamStation.

Stores device information, credentials, and settings locally.
"""

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging

from models.device import Device, Camera

logger = logging.getLogger(__name__)

Base = declarative_base()


class DeviceDB(Base):
    """Database model for devices."""
    
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    port = Column(Integer, default=80)
    rtsp_port = Column(Integer, default=554)
    username = Column(String, default="admin")
    password = Column(String, default="")  # TODO: Encrypt this
    
    device_type = Column(String, default="unknown")
    model = Column(String)
    serial_number = Column(String)
    firmware_version = Column(String)
    mac_address = Column(String)
    
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime)
    
    has_lpr = Column(Boolean, default=False)
    max_channels = Column(Integer, default=1)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    cameras = relationship("CameraDB", back_populates="device", cascade="all, delete-orphan")


class CameraDB(Base):
    """Database model for cameras/channels."""

    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    channel_number = Column(Integer, nullable=False)
    name = Column(String, nullable=False)

    is_online = Column(Boolean, default=True)
    has_ptz = Column(Boolean, default=False)
    has_audio = Column(Boolean, default=False)
    has_lpr = Column(Boolean, default=False)
    resolution = Column(String)

    stream_type = Column(String, default="main")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device = relationship("DeviceDB", back_populates="cameras")
    lpr_events = relationship("LPREventDB", back_populates="camera", cascade="all, delete-orphan")


class LPREventDB(Base):
    """Database model for LPR (License Plate Recognition) events."""

    __tablename__ = "lpr_events"

    id = Column(Integer, primary_key=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)

    plate_number = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    confidence = Column(Float, default=0.0)

    plate_color = Column(String)
    vehicle_color = Column(String)
    vehicle_type = Column(String)
    direction = Column(String)  # in, out, unknown

    snapshot_path = Column(String)  # Full image
    plate_snapshot_path = Column(String)  # Cropped plate image

    created_at = Column(DateTime, default=datetime.utcnow)

    camera = relationship("CameraDB", back_populates="lpr_events")


class Database:
    """Database manager for CamStation."""
    
    def __init__(self, db_path: Path):
        """
        Initialize database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.Session = sessionmaker(bind=self.engine)
    
    def close(self):
        """Close database connection."""
        self.engine.dispose()
    
    # === Device Operations ===
    
    def add_device(self, device: Device) -> int:
        """
        Add a new device to the database.
        
        Returns:
            The new device ID
        """
        session = self.Session()
        try:
            db_device = DeviceDB(
                name=device.name,
                ip_address=device.ip_address,
                port=device.port,
                rtsp_port=device.rtsp_port,
                username=device.username,
                password=device.password,
                device_type=device.device_type,
                model=device.model,
                serial_number=device.serial_number,
                firmware_version=device.firmware_version,
                mac_address=device.mac_address,
                has_lpr=device.has_lpr,
                max_channels=device.max_channels
            )
            
            session.add(db_device)
            session.commit()
            
            device_id = db_device.id
            
            # Add cameras
            for camera in device.cameras:
                self.add_camera(camera, device_id, session)
            
            session.commit()
            return device_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error adding device: {e}")
            raise
        finally:
            session.close()
    
    def get_device(self, device_id: int) -> Optional[Device]:
        """Get a device by ID."""
        session = self.Session()
        try:
            db_device = session.query(DeviceDB).filter_by(id=device_id).first()
            if not db_device:
                return None
            
            return self._db_to_device(db_device)
            
        finally:
            session.close()
    
    def get_all_devices(self) -> List[Device]:
        """Get all devices."""
        session = self.Session()
        try:
            db_devices = session.query(DeviceDB).all()
            return [self._db_to_device(d) for d in db_devices]
            
        finally:
            session.close()
    
    def update_device(self, device: Device):
        """Update a device."""
        session = self.Session()
        try:
            db_device = session.query(DeviceDB).filter_by(id=device.id).first()
            if not db_device:
                return
            
            db_device.name = device.name
            db_device.ip_address = device.ip_address
            db_device.port = device.port
            db_device.rtsp_port = device.rtsp_port
            db_device.username = device.username
            db_device.password = device.password
            db_device.device_type = device.device_type
            db_device.model = device.model
            db_device.serial_number = device.serial_number
            db_device.firmware_version = device.firmware_version
            db_device.is_online = device.is_online
            db_device.last_seen = device.last_seen
            db_device.has_lpr = device.has_lpr
            
            session.commit()
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating device: {e}")
            raise
        finally:
            session.close()
    
    def delete_device(self, device_id: int):
        """Delete a device and its cameras."""
        session = self.Session()
        try:
            db_device = session.query(DeviceDB).filter_by(id=device_id).first()
            if db_device:
                session.delete(db_device)
                session.commit()
                
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting device: {e}")
            raise
        finally:
            session.close()
    
    # === Camera Operations ===
    
    def add_camera(self, camera: Camera, device_id: int, session=None):
        """Add a camera to a device."""
        own_session = session is None
        if own_session:
            session = self.Session()
        
        try:
            db_camera = CameraDB(
                device_id=device_id,
                channel_number=camera.channel_number,
                name=camera.name,
                is_online=camera.is_online,
                has_ptz=camera.has_ptz,
                has_audio=camera.has_audio,
                has_lpr=camera.has_lpr,
                resolution=camera.resolution,
                stream_type=camera.stream_type
            )
            
            session.add(db_camera)
            
            if own_session:
                session.commit()
                
        except Exception as e:
            if own_session:
                session.rollback()
            logger.error(f"Error adding camera: {e}")
            raise
        finally:
            if own_session:
                session.close()
    
    def get_camera(self, camera_id: int) -> Optional[Camera]:
        """Get a camera by ID."""
        session = self.Session()
        try:
            db_camera = session.query(CameraDB).filter_by(id=camera_id).first()
            if not db_camera:
                return None
            
            # Get parent device for RTSP URL construction
            device = self._db_to_device(db_camera.device)
            
            return self._db_to_camera(db_camera, device)
            
        finally:
            session.close()
    
    def get_cameras_for_device(self, device_id: int) -> List[Camera]:
        """Get all cameras for a device."""
        session = self.Session()
        try:
            db_device = session.query(DeviceDB).filter_by(id=device_id).first()
            if not db_device:
                return []
            
            device = self._db_to_device(db_device)
            return [self._db_to_camera(c, device) for c in db_device.cameras]
            
        finally:
            session.close()
    
    def update_device_status(self, device_id: int, is_online: bool):
        """Update device online status."""
        session = self.Session()
        try:
            db_device = session.query(DeviceDB).filter_by(id=device_id).first()
            if db_device:
                db_device.is_online = is_online
                if is_online:
                    db_device.last_seen = datetime.utcnow()
                session.commit()
                
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating device status: {e}")
        finally:
            session.close()
    
    # === Conversion Helpers ===
    
    def _db_to_device(self, db_device: DeviceDB) -> Device:
        """Convert database device to model."""
        device = Device(
            id=db_device.id,
            name=db_device.name,
            ip_address=db_device.ip_address,
            port=db_device.port,
            rtsp_port=db_device.rtsp_port,
            username=db_device.username,
            password=db_device.password,
            device_type=db_device.device_type,
            model=db_device.model,
            serial_number=db_device.serial_number,
            firmware_version=db_device.firmware_version,
            mac_address=db_device.mac_address,
            is_online=db_device.is_online,
            last_seen=db_device.last_seen,
            has_lpr=db_device.has_lpr,
            max_channels=db_device.max_channels
        )
        
        # Add cameras
        for db_camera in db_device.cameras:
            device.cameras.append(self._db_to_camera(db_camera, device))
        
        return device
    
    def _db_to_camera(self, db_camera: CameraDB, device: Device) -> Camera:
        """Convert database camera to model."""
        # Construct RTSP URLs
        base_rtsp = device.get_rtsp_base_url()
        channel = db_camera.channel_number

        rtsp_url = f"{base_rtsp}/Streaming/Channels/{channel}01"
        rtsp_url_sub = f"{base_rtsp}/Streaming/Channels/{channel}02"

        return Camera(
            id=db_camera.id,
            device_id=db_camera.device_id,
            channel_number=db_camera.channel_number,
            name=db_camera.name,
            rtsp_url=rtsp_url,
            rtsp_url_sub=rtsp_url_sub,
            is_online=db_camera.is_online,
            has_ptz=db_camera.has_ptz,
            has_audio=db_camera.has_audio,
            has_lpr=db_camera.has_lpr,
            resolution=db_camera.resolution,
            stream_type=db_camera.stream_type
        )

    # === LPR Event Operations ===

    def add_lpr_event(self, camera_id: int, plate_number: str, timestamp: datetime,
                      confidence: float = 0.0, plate_color: str = None,
                      vehicle_color: str = None, vehicle_type: str = None,
                      direction: str = None, snapshot_path: str = None,
                      plate_snapshot_path: str = None) -> int:
        """
        Add an LPR event to the database.

        Returns:
            The new event ID
        """
        session = self.Session()
        try:
            db_event = LPREventDB(
                camera_id=camera_id,
                plate_number=plate_number.upper(),
                timestamp=timestamp,
                confidence=confidence,
                plate_color=plate_color,
                vehicle_color=vehicle_color,
                vehicle_type=vehicle_type,
                direction=direction,
                snapshot_path=snapshot_path,
                plate_snapshot_path=plate_snapshot_path
            )

            session.add(db_event)
            session.commit()
            return db_event.id

        except Exception as e:
            session.rollback()
            logger.error(f"Error adding LPR event: {e}")
            raise
        finally:
            session.close()

    def search_lpr_events(self, start_time: datetime = None, end_time: datetime = None,
                          plate_number: str = None, camera_id: int = None,
                          direction: str = None, limit: int = 100,
                          offset: int = 0) -> List[Dict]:
        """
        Search for LPR events.

        Args:
            start_time: Search start time (optional)
            end_time: Search end time (optional)
            plate_number: Plate number filter with wildcards (optional)
            camera_id: Filter by camera (optional)
            direction: Filter by direction (in/out) (optional)
            limit: Maximum results
            offset: Result offset for pagination

        Returns:
            List of LPR events as dictionaries
        """
        session = self.Session()
        try:
            query = session.query(LPREventDB)

            if start_time:
                query = query.filter(LPREventDB.timestamp >= start_time)
            if end_time:
                query = query.filter(LPREventDB.timestamp <= end_time)
            if plate_number:
                # Support wildcards with * or %
                plate_filter = plate_number.replace('*', '%').upper()
                query = query.filter(LPREventDB.plate_number.like(plate_filter))
            if camera_id:
                query = query.filter(LPREventDB.camera_id == camera_id)
            if direction:
                query = query.filter(LPREventDB.direction == direction)

            # Order by timestamp descending (newest first)
            query = query.order_by(LPREventDB.timestamp.desc())

            # Apply pagination
            query = query.offset(offset).limit(limit)

            results = []
            for event in query.all():
                # Get camera name
                camera = session.query(CameraDB).filter_by(id=event.camera_id).first()
                camera_name = camera.name if camera else "Unknown"

                results.append({
                    'id': event.id,
                    'camera_id': event.camera_id,
                    'camera_name': camera_name,
                    'plate_number': event.plate_number,
                    'timestamp': event.timestamp,
                    'confidence': event.confidence,
                    'plate_color': event.plate_color,
                    'vehicle_color': event.vehicle_color,
                    'vehicle_type': event.vehicle_type,
                    'direction': event.direction,
                    'snapshot_path': event.snapshot_path,
                    'plate_snapshot_path': event.plate_snapshot_path
                })

            return results

        finally:
            session.close()

    def get_lpr_event_count(self, start_time: datetime = None, end_time: datetime = None,
                            plate_number: str = None, camera_id: int = None) -> int:
        """Get count of LPR events matching criteria."""
        session = self.Session()
        try:
            query = session.query(LPREventDB)

            if start_time:
                query = query.filter(LPREventDB.timestamp >= start_time)
            if end_time:
                query = query.filter(LPREventDB.timestamp <= end_time)
            if plate_number:
                plate_filter = plate_number.replace('*', '%').upper()
                query = query.filter(LPREventDB.plate_number.like(plate_filter))
            if camera_id:
                query = query.filter(LPREventDB.camera_id == camera_id)

            return query.count()

        finally:
            session.close()

    def get_unique_plates(self, start_time: datetime = None, end_time: datetime = None,
                          camera_id: int = None) -> List[str]:
        """Get list of unique plate numbers."""
        session = self.Session()
        try:
            query = session.query(LPREventDB.plate_number).distinct()

            if start_time:
                query = query.filter(LPREventDB.timestamp >= start_time)
            if end_time:
                query = query.filter(LPREventDB.timestamp <= end_time)
            if camera_id:
                query = query.filter(LPREventDB.camera_id == camera_id)

            return [row[0] for row in query.all()]

        finally:
            session.close()

    def delete_lpr_event(self, event_id: int):
        """Delete an LPR event."""
        session = self.Session()
        try:
            event = session.query(LPREventDB).filter_by(id=event_id).first()
            if event:
                session.delete(event)
                session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting LPR event: {e}")
        finally:
            session.close()

    def cleanup_old_lpr_events(self, days_to_keep: int = 30):
        """Delete LPR events older than specified days."""
        session = self.Session()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
            session.query(LPREventDB).filter(LPREventDB.timestamp < cutoff).delete()
            session.commit()
            logger.info(f"Cleaned up LPR events older than {days_to_keep} days")

        except Exception as e:
            session.rollback()
            logger.error(f"Error cleaning up LPR events: {e}")
        finally:
            session.close()
