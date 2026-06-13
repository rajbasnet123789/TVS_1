export interface User {
  id: string
  email: string
  full_name: string | null
  role: Role
  is_active: boolean
  last_login: string | null
  created_at: string
}

export interface Role {
  id: string
  name: string
  description: string | null
  permissions: string[]
}

export interface Camera {
  id: string
  name: string
  rtsp_url: string
  onvif_address: string | null
  location: string | null
  zone: string | null
  status: string
  fps_target: number
  resolution_width: number
  resolution_height: number
  enabled: boolean
  discovered_via_onvif: boolean
  hls_url: string | null
  username: string | null
  password: string | null
  created_at: string
}

export interface Chicken {
  id: string
  chicken_id: number
  name: string | null
  breed: string | null
  status: string
  notes: string | null
  created_at: string
  updated_at: string
}

export interface ONVIFChannel {
  channel: number
  profile_token: string
  rtsp_url: string | null
  name: string | null
  encoding: string | null
  resolution_width: number | null
  resolution_height: number | null
}

export interface ONVIFDevice {
  ip: string
  manufacturer: string | null
  model: string | null
  brand: string | null
  rtsp_url: string | null
  onvif_address: string | null
  device_service_url: string | null
  channels: ONVIFChannel[]
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface DetectionStats {
  total_detections: number
  unique_chickens: number
  detections_per_minute: number
  active_cameras: number
}

export interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

export interface TimeSeriesPoint {
  time: string
  value: number
}

export interface DetectionHistory {
  camera_id: string
  window: string
  detection_series: TimeSeriesPoint[]
  headcount_series: TimeSeriesPoint[]
}

export interface DetectionSummary {
  total_detections: number
  unique_chickens: number
  peak_head_count: number
  avg_confidence: number
  active_minutes: number
  detections_per_hour: number
}

export interface DetectedChicken {
  track_id: number
  detections: number
  avg_confidence: number
  last_seen: string
  first_seen: string
  cameras: string[]
  status: string
}
