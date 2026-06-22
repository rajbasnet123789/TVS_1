export interface Farm {
  id: string
  name: string
  location: string | null
  slug: string
  settings: Record<string, unknown>
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface User {
  id: string
  email: string
  full_name: string | null
  role: Role
  farm_id: string | null
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
  location: string | null
  zone: string | null
  status: string
  fps_target: number
  resolution_width: number
  resolution_height: number
  enabled: boolean
  hls_url: string | null
  username: string | null
  password: string | null
  coop_id: string | null
  snapshot_url: string | null
  roi: number[][] | null
  created_at: string
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

export interface DiscoveredDevice {
  name: string
  device_url: string
  ip: string
  xaddrs: string
  types: string
  scopes: string
}

export interface ScanStatus {
  scanning: boolean
  progress: number | null
  devices_found: number
  error: string | null
}

export interface CostBreakdown {
  chick_purchase_cost: number
  feed_cost: number
  labour_cost: number
  other_costs: number
  total_costs: number
}

export interface ProfitLossResult {
  input_chickens: number
  projected_headcount: number
  estimated_mortality_rate: number
  price_per_chicken: number
  duration_days: number
  revenue: number
  costs: CostBreakdown
  net_profit: number
  profit_margin_percent: number
  is_profitable: boolean
  avg_health_score: number | null
  current_headcount: number | null
}
