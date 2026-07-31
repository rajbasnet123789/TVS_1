// Hardcoded demo data for mortality detections so the app looks real without
// a live health/mortality model. The photos live in frontend/public/mortality/.

export interface DemoAlert {
  id: string
  camera_id: string | null
  chicken_id: string | null
  track_id: string | null
  type: string
  severity: number
  message: string
  created_at: string
  acknowledged_at: string | null
}

export interface DemoMedia {
  key: string
  url: string
  label: string
}const MORTALITY_PHOTOS = [
  '/mortality/Mortality.jpg',
  '/mortality/Mortality2.jpg',
]

const now = Date.now()
const minsAgo = (m: number) => new Date(now - m * 60_000).toISOString()

export function isDemoAlert(id: string): boolean {
  return id.startsWith('demo-mortality-')
}

export function buildMortalityAlerts(cameraIds: (string | null)[] = []): DemoAlert[] {
  const cam = (i: number) => cameraIds[i] ?? null
  return [
    {
      id: 'demo-mortality-001',
      camera_id: cam(0),
      chicken_id: null,
      track_id: null,
      type: 'mortality',
      severity: 2,
      message: 'Dead chicken detected near feeding line — 1 bird, confidence 94%',
      created_at: minsAgo(125),
      acknowledged_at: null,
    },
    {
      id: 'demo-mortality-002',
      camera_id: cam(1),
      chicken_id: null,
      track_id: null,
      type: 'mortality',
      severity: 1,
      message: 'Possible dead chicken detected beside the water line — 1 bird, confidence 81%',
      created_at: minsAgo(430),
      acknowledged_at: minsAgo(300),
    },
  ]
}

export function buildMortalityMedia(): DemoMedia[] {
  return [
    {
      key: 'snapshots/192.168.31.169 - Ch 5/2026-08-01_07-42-00_mortality.jpg',
      url: MORTALITY_PHOTOS[0],
      label: '192.168.31.169 - Ch 5',
    },
    {
      key: 'snapshots/192.168.31.169 - Ch 5/2026-08-01_06-10-00_mortality.jpg',
      url: MORTALITY_PHOTOS[1],
      label: '192.168.31.169 - Ch 5',
    },
  ]
}
