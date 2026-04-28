import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  AlertTriangle,
  Braces,
  Cable,
  Check,
  Cpu,
  DoorOpen,
  Hand,
  Home,
  ListTree,
  Pause,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Route,
  Search,
  Send,
  Square,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react'

const DEFAULT_API_BASE = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''
const API_BASE = import.meta.env.VITE_OMX_API_BASE ?? DEFAULT_API_BASE
const WS_BASE =
  import.meta.env.VITE_OMX_WS_BASE ??
  (API_BASE
    ? API_BASE.replace(/^http/, 'ws')
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`)

type ConnectionState = 'connecting' | 'online' | 'offline'
type PlanState = 'idle' | 'valid' | 'error'
type HardwareMode = 'mock' | 'real'
type ConsoleMode = 'joints' | 'ros'
type RosResourceKind = 'topics' | 'services' | 'actions'
type JointMap = Record<string, number>

type EventLogEntry = {
  id: number
  at: string
  state: PlanState
  message: string
}

type RobotInfo = {
  robot: string
  arm_joints: string[]
  gripper_command_joint: string
  named_states: string[]
  limits: {
    joints: Record<string, { lower?: number; upper?: number; velocity?: number }>
  }
}

type HealthResponse = {
  ok: boolean
  ros?: {
    joint_states_seen: boolean
    last_joint_state_age_sec: number | null
    joint_state_topic: string
    error: string | null
  }
  websocket_clients?: number
}

type JointStateMessage = {
  type: 'joint_state'
  stamp: number
  frame_id: string
  joints: JointMap
  source: string
}

type UnityBuildManifest = {
  available: boolean
  loaderUrl: string
  dataUrl: string
  frameworkUrl: string
  codeUrl: string
}

type LaunchResponse = {
  ok: boolean
  code: string
  message: string
  status?: {
    running: boolean
    mode: HardwareMode | null
    pid: number | null
    hardware_port: string | null
  }
}

type LaunchStatusResponse = {
  ok: boolean
  status?: {
    running: boolean
    mode: HardwareMode | null
  }
}

type MotionResponse = {
  ok: boolean
  message: string
  plan_id?: string
  mode?: string
  duration?: number
  point_count?: number
  invalid_joints?: string[]
  trajectory?: PlannedTrajectory
}

type RosGraphEntry = {
  name: string
  types: string[]
  request_example?: Record<string, unknown>
  goal_example?: Record<string, unknown>
}

type RosGraphResponse = {
  ok: boolean
  message?: string
  ros_domain_id?: string
  topics: RosGraphEntry[]
  services: RosGraphEntry[]
  actions: RosGraphEntry[]
}

type RosCommandResponse = {
  ok: boolean
  message: string
  response?: unknown
  result?: unknown
}

type RosImageFrame = {
  type: 'image_frame' | 'image_error'
  topic?: string
  topic_type?: string
  stamp?: number | null
  width?: number
  height?: number
  encoding?: string
  step?: number
  data?: string
  data_url?: string
  message?: string
}

type PlannedTrajectory = {
  joint_names: string[]
  positions: number[]
  times: number[]
}

const FALLBACK_INFO: RobotInfo = {
  robot: 'omx_f',
  arm_joints: ['joint1', 'joint2', 'joint3', 'joint4', 'joint5'],
  gripper_command_joint: 'gripper_joint_1',
  named_states: ['init', 'home', 'ready', 'stow', 'pre_grasp', 'open', 'close'],
  limits: {
    joints: {
      joint1: { lower: -6.283185307179586, upper: 6.283185307179586 },
      joint2: { lower: -6.283185307179586, upper: 6.283185307179586 },
      joint3: { lower: -6.283185307179586, upper: 6.283185307179586 },
      joint4: { lower: -6.283185307179586, upper: 6.283185307179586 },
      joint5: { lower: -6.283185307179586, upper: 6.283185307179586 },
      gripper_joint_1: { lower: 0, upper: 1 },
    },
  },
}

const NAMED_TARGETS: Record<string, JointMap> = {
  init: { joint1: 0, joint2: 0, joint3: 0, joint4: 0, joint5: 0 },
  home: { joint1: 0, joint2: -1.57, joint3: 1.57, joint4: 1.57, joint5: 0 },
  open: { gripper_joint_1: 1 },
  close: { gripper_joint_1: 0 },
}

const ACTION_NAMES = ['home', 'init', 'open', 'close'] as const
const HOME_READY_TOLERANCE_RAD = 0.05
const HOME_READY_STABLE_SAMPLES = 4

const formatRad = (value?: number) =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '...'

const formatDeg = (value?: number) =>
  typeof value === 'number' && Number.isFinite(value)
    ? `${((value * 180) / Math.PI).toFixed(0)} deg`
    : '...'

const radToDeg = (value: number) => (value * 180) / Math.PI
const degToRad = (value: number) => (value * Math.PI) / 180

const formatLogTime = () =>
  new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date())

const responseErrorLabel = (message: string) =>
  message.includes('/ros/graph returned 404')
    ? 'ROS graph unavailable: backend restart required'
    : `ROS graph unavailable (${message})`

const LOCAL_ROS_REQUEST_EXAMPLES: Record<string, Record<string, unknown>> = {
  'omx_interfaces/srv/PlanToJoints': {
    joint_names: ['joint1', 'joint2', 'joint3', 'joint4', 'joint5'],
    positions: [0.0, -1.0, 1.0, 0.5, 0.0],
    velocity_scale: 0.2,
  },
  'omx_interfaces/srv/ExecutePlan': {
    plan_id: 'paste_plan_id_from_plan_to_joints',
  },
  'omx_interfaces/srv/ClearPlan': {},
  'omx_interfaces/srv/GetBlockPoses': {
    color: 'red',
  },
  'omx_interfaces/srv/GetTop4Keypoints': {
    publish_debug: true,
  },
}

const MOVE_TO_POSE_GOAL_EXAMPLE = {
  target_pose: {
    header: {
      frame_id: 'world',
    },
    pose: {
      position: {
        x: 0.33128309872740647,
        y: 0.008654711230646865,
        z: 0.15,
      },
      orientation: {
        x: 0.0,
        y: 0.0,
        z: 0.0,
        w: 1.0,
      },
    },
  },
  velocity_scale: 0.2,
  plan_only: false,
  preview_in_sim: false,
}

const LOCAL_ROS_GOAL_EXAMPLES: Record<string, Record<string, unknown>> = {
  '/omx/move_to_pose': MOVE_TO_POSE_GOAL_EXAMPLE,
  'omx_interfaces/action/MoveToPose': MOVE_TO_POSE_GOAL_EXAMPLE,
  'omx_interfaces/action/MoveToJoints': {
    joint_names: ['joint1', 'joint2', 'joint3', 'joint4', 'joint5'],
    positions: [0.0, -1.0, 1.0, 0.5, 0.0],
    velocity_scale: 0.2,
  },
  'omx_interfaces/action/MoveToNamed': {
    name: 'home',
  },
  'omx_interfaces/action/GripperCommand': {
    position: 1.0,
    max_effort: 0.0,
  },
  'omx_interfaces/action/PickDetected': {
    object_color: 'red',
    retry_on_fail: true,
  },
  'omx_interfaces/action/PickPlace': {
    object_color: 'red',
    target_box: 'left',
    retry_on_fail: true,
  },
}

const rosCommandExampleFor = (kind: Exclude<RosResourceKind, 'topics'>, entry: RosGraphEntry) => {
  const selectedType = entry.types[0] ?? ''
  const graphExample = kind === 'services' ? entry.request_example : entry.goal_example
  const localExamples = kind === 'services' ? LOCAL_ROS_REQUEST_EXAMPLES : LOCAL_ROS_GOAL_EXAMPLES
  return graphExample ?? localExamples[entry.name] ?? localExamples[selectedType] ?? {}
}

const formatRosCommandExample = (kind: Exclude<RosResourceKind, 'topics'>, entry: RosGraphEntry) =>
  JSON.stringify(rosCommandExampleFor(kind, entry), null, 2)

const clampByte = (value: number) => Math.max(0, Math.min(255, value))

const yuvToRgb = (y: number, u: number, v: number) => {
  const c = y - 16
  const d = u - 128
  const e = v - 128
  return {
    r: clampByte((298 * c + 409 * e + 128) >> 8),
    g: clampByte((298 * c - 100 * d - 208 * e + 128) >> 8),
    b: clampByte((298 * c + 516 * d + 128) >> 8),
  }
}

const withMimicGripper = (joints: JointMap, gripperCommandJoint: string) => {
  const next = { ...joints }
  const gripper = next[gripperCommandJoint]
  if (typeof gripper === 'number') {
    next.gripper_joint_2 = -gripper
  }
  return next
}

const readMotionResponse = async (response: Response) => {
  const text = await response.text()
  let data: MotionResponse
  try {
    data = text
      ? (JSON.parse(text) as MotionResponse)
      : { ok: response.ok, message: response.statusText || `HTTP ${response.status}` }
  } catch {
    data = { ok: false, message: text || response.statusText || `HTTP ${response.status}` }
  }

  if (!response.ok || !data.ok) {
    throw new Error(data.message || `HTTP ${response.status}`)
  }
  return data
}

function OmxConsole() {
  const [robotInfo, setRobotInfo] = useState<RobotInfo>(FALLBACK_INFO)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const [currentJoints, setCurrentJoints] = useState<JointMap>({})
  const [targetJoints, setTargetJoints] = useState<JointMap>({})
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null)
  const [planState, setPlanState] = useState<PlanState>('idle')
  const [activePlanId, setActivePlanId] = useState<string | null>(null)
  const [trajectorySummary, setTrajectorySummary] = useState<string | null>(null)
  const [motionBusy, setMotionBusy] = useState(false)
  const [editingDegreeJoint, setEditingDegreeJoint] = useState<string | null>(null)
  const [degreeDraft, setDegreeDraft] = useState('')
  const [eventLogs, setEventLogs] = useState<EventLogEntry[]>([
    { id: 1, at: formatLogTime(), state: 'idle', message: 'Console ready' },
  ])
  const [targetPreviewActive, setTargetPreviewActive] = useState(false)
  const [launchMode, setLaunchMode] = useState<HardwareMode | null>(null)
  const [launchBusy, setLaunchBusy] = useState(false)
  const [systemNotice, setSystemNotice] = useState<string | null>(null)
  const [consoleMode, setConsoleMode] = useState<ConsoleMode>('joints')
  const [rosGraph, setRosGraph] = useState<RosGraphResponse | null>(null)
  const [rosGraphBusy, setRosGraphBusy] = useState(false)
  const [rosGraphError, setRosGraphError] = useState<string | null>(null)
  const [rosKind, setRosKind] = useState<RosResourceKind>('topics')
  const [selectedRosName, setSelectedRosName] = useState<string | null>(null)
  const [rosDomainDraft, setRosDomainDraft] = useState('')
  const [rosRequestDraft, setRosRequestDraft] = useState('{}')
  const [rosRequestTouched, setRosRequestTouched] = useState(false)
  const [rosCommandBusy, setRosCommandBusy] = useState(false)
  const [rosCommandOutput, setRosCommandOutput] = useState<string | null>(null)
  const targetTouched = useRef(false)
  const noticeTimer = useRef<number | undefined>(undefined)
  const eventLogSeq = useRef(1)
  const eventLogListRef = useRef<HTMLDivElement | null>(null)
  const launchModeRef = useRef<HardwareMode | null>(null)
  const unloadStopSent = useRef(false)
  const launchReadyMode = useRef<HardwareMode | null>(null)
  const launchReadyStartedAt = useRef(0)
  const launchReadyStableSamples = useRef(0)
  const previousRosSelectionKey = useRef(`${rosKind}:${selectedRosName ?? ''}`)

  const controlJoints = useMemo(
    () => [...robotInfo.arm_joints, robotInfo.gripper_command_joint],
    [robotInfo],
  )

  const appendEventLog = useCallback((state: PlanState, message: string) => {
    setEventLogs((previous) => {
      const last = previous[previous.length - 1]
      if (last?.state === state && last.message === message) return previous

      eventLogSeq.current += 1
      return [
        ...previous.slice(-159),
        {
          id: eventLogSeq.current,
          at: formatLogTime(),
          state,
          message,
        },
      ]
    })
  }, [])

  const resetEventLogs = useCallback(() => {
    setEventLogs([])
  }, [])

  const setConsoleStatus = useCallback(
    (state: PlanState, message: string) => {
      setPlanState(state)
      appendEventLog(state, message)
    },
    [appendEventLog],
  )

  useEffect(() => {
    const list = eventLogListRef.current
    if (!list) return
    list.scrollTop = list.scrollHeight
  }, [eventLogs])

  useEffect(() => {
    launchModeRef.current = launchMode
    if (launchMode !== null) {
      unloadStopSent.current = false
    }
  }, [launchMode])

  const requestLaunchStopForPageExit = useCallback(() => {
    if (launchModeRef.current === null || unloadStopSent.current) return
    unloadStopSent.current = true

    const stopUrl = `${API_BASE}/robot/launch/stop`
    if (navigator.sendBeacon?.(stopUrl)) return

    void fetch(stopUrl, {
      method: 'POST',
      keepalive: true,
    }).catch(() => undefined)
  }, [])

  useEffect(() => {
    window.addEventListener('pagehide', requestLaunchStopForPageExit)
    window.addEventListener('beforeunload', requestLaunchStopForPageExit)

    return () => {
      window.removeEventListener('pagehide', requestLaunchStopForPageExit)
      window.removeEventListener('beforeunload', requestLaunchStopForPageExit)
    }
  }, [requestLaunchStopForPageExit])

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/robot/info`, { signal: controller.signal })
      .then((response) => response.json())
      .then((info: RobotInfo) => setRobotInfo(info))
      .catch(() => setRobotInfo(FALLBACK_INFO))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    let cancelled = false
    const poll = () => {
      fetch(`${API_BASE}/health`)
        .then((response) => response.json())
        .then((data: HealthResponse) => {
          if (!cancelled) setHealth(data)
        })
        .catch(() => {
          if (!cancelled) setHealth(null)
        })
    }

    poll()
    const timer = window.setInterval(poll, 2000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let disposed = false

    const connect = () => {
      setConnection('connecting')
      socket = new WebSocket(`${WS_BASE}/ws/state`)
      socket.onopen = () => setConnection('online')
      socket.onclose = () => {
        setConnection('offline')
        if (!disposed) reconnectTimer = window.setTimeout(connect, 1500)
      }
      socket.onerror = () => setConnection('offline')
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as JointStateMessage & {
          action?: string
          progress?: number
          status?: string
          ok?: boolean
          message?: string
        }
        if (message.type !== 'joint_state') {
          if (message.type === 'action_feedback') {
            const progress =
              typeof message.progress === 'number' ? ` ${Math.round(message.progress * 100)}%` : ''
            appendEventLog('idle', `${message.action ?? 'motion'} ${message.status ?? 'feedback'}${progress}`)
          }
          if (message.type === 'action_result') {
            appendEventLog(
              message.ok ? 'valid' : 'error',
              `${message.action ?? 'motion'} ${message.message ?? 'completed'}`,
            )
          }
          return
        }

        setCurrentJoints(message.joints)
        setLastMessageAt(Date.now())
        setTargetJoints((previous) => {
          let next = previous
          for (const [joint, value] of Object.entries(message.joints)) {
            if (typeof value !== 'number') continue
            if (typeof next[joint] === 'number') continue
            if (next === previous) next = { ...previous }
            next[joint] = value
          }
          return next
        })
      }
    }

    connect()
    return () => {
      disposed = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [appendEventLog])

  const refreshLaunchStatus = useCallback(() => {
    fetch(`${API_BASE}/robot/launch/status`)
      .then((response) => response.json())
      .then((data: LaunchStatusResponse) => {
        setLaunchMode(data.status?.running ? data.status.mode ?? null : null)
      })
      .catch(() => setLaunchMode(null))
  }, [])

  const refreshRosGraph = useCallback(async () => {
    setRosGraphBusy(true)
    setRosGraphError(null)
    try {
      const response = await fetch(`${API_BASE}/ros/graph`)
      const data = (await response.json()) as RosGraphResponse
      if (!response.ok || !data.ok) {
        const detail =
          response.status === 404
            ? 'Backend API is not updated or not restarted. /ros/graph returned 404.'
            : data.message || `HTTP ${response.status}`
        throw new Error(detail)
      }
      setRosGraph(data)
      setRosDomainDraft(data.ros_domain_id ?? '')
      setSelectedRosName((previous) => {
        const resources = data[rosKind]
        if (previous && resources.some((entry) => entry.name === previous)) return previous
        return resources[0]?.name ?? null
      })
      appendEventLog('idle', 'ROS graph refreshed')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed'
      setRosGraphError(message)
      appendEventLog('error', responseErrorLabel(message))
    } finally {
      setRosGraphBusy(false)
    }
  }, [appendEventLog, rosKind])

  const handleRosKindChange = useCallback(
    (nextKind: RosResourceKind) => {
      setRosKind(nextKind)
      const resources = rosGraph?.[nextKind] ?? []
      const nextSelection = resources[0] ?? null
      setSelectedRosName(nextSelection?.name ?? null)
      setRosRequestTouched(false)
      setRosRequestDraft(
        nextKind !== 'topics' && nextSelection ? formatRosCommandExample(nextKind, nextSelection) : '{}',
      )
      setRosCommandOutput(null)
    },
    [rosGraph],
  )

  const handleRosSelectName = useCallback(
    (name: string) => {
      setSelectedRosName(name)
      setRosRequestTouched(false)
      setRosCommandOutput(null)
      const selected = rosGraph?.[rosKind].find((entry) => entry.name === name)
      setRosRequestDraft(rosKind !== 'topics' && selected ? formatRosCommandExample(rosKind, selected) : '{}')
    },
    [rosGraph, rosKind],
  )

  const handleRosRequestDraftChange = useCallback((value: string) => {
    setRosRequestDraft(value)
    setRosRequestTouched(true)
  }, [])

  useEffect(() => {
    const selectionKey = `${rosKind}:${selectedRosName ?? ''}`
    if (previousRosSelectionKey.current === selectionKey) return
    previousRosSelectionKey.current = selectionKey
    setRosRequestTouched(false)
  }, [rosKind, selectedRosName])

  useEffect(() => {
    if (rosKind === 'topics' || rosRequestTouched) return

    const selected = rosGraph?.[rosKind].find((entry) => entry.name === selectedRosName)
    if (selected) {
      setRosRequestDraft(formatRosCommandExample(rosKind, selected))
    }
  }, [rosGraph, rosKind, rosRequestTouched, selectedRosName])

  const saveRosDomain = useCallback(async () => {
    try {
      setRosCommandBusy(true)
      const response = await fetch(`${API_BASE}/ros/domain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ros_domain_id: rosDomainDraft.trim() }),
      })
      const data = (await response.json()) as RosCommandResponse & { ros_domain_id?: string }
      if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`)
      setRosDomainDraft(data.ros_domain_id ?? rosDomainDraft.trim())
      setConsoleStatus('idle', data.message || 'ROS_DOMAIN_ID updated')
      await refreshRosGraph()
    } catch (error) {
      setConsoleStatus(
        'error',
        `ROS_DOMAIN_ID update failed (${error instanceof Error ? error.message : 'failed'})`,
      )
    } finally {
      setRosCommandBusy(false)
    }
  }, [refreshRosGraph, rosDomainDraft, setConsoleStatus])

  const sendRosCommand = useCallback(async () => {
    if (!selectedRosName || !rosGraph) return
    const selected = rosGraph[rosKind].find((entry) => entry.name === selectedRosName)
    const selectedType = selected?.types[0]
    if (!selectedType) {
      setConsoleStatus('error', 'Selected ROS resource has no type')
      return
    }

    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(rosRequestDraft || '{}') as Record<string, unknown>
    } catch {
      setConsoleStatus('error', 'Request JSON is invalid')
      return
    }

    if (rosKind === 'topics') {
      setConsoleStatus('idle', `${selectedRosName} selected`)
      setRosCommandOutput(
        JSON.stringify(
          {
            topic: selectedRosName,
            type: selectedType,
            note: 'Image topic selected. Browser video streaming is not attached yet.',
          },
          null,
          2,
        ),
      )
      return
    }

    try {
      setRosCommandBusy(true)
      const endpoint = rosKind === 'services' ? '/ros/service-call' : '/ros/action-goal'
      const body =
        rosKind === 'services'
          ? { name: selectedRosName, type: selectedType, request: payload }
          : { name: selectedRosName, type: selectedType, goal: payload }
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = (await response.json()) as RosCommandResponse
      if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`)
      setConsoleStatus('valid', data.message || `${selectedRosName} completed`)
      setRosCommandOutput(JSON.stringify(data.response ?? data.result ?? data, null, 2))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed'
      setConsoleStatus('error', `ROS command failed (${message})`)
      setRosCommandOutput(JSON.stringify({ ok: false, message }, null, 2))
    } finally {
      setRosCommandBusy(false)
    }
  }, [rosGraph, rosKind, rosRequestDraft, selectedRosName, setConsoleStatus])

  useEffect(() => {
    refreshLaunchStatus()
    const launchStatusTimer = window.setInterval(refreshLaunchStatus, 2000)

    return () => {
      window.clearInterval(launchStatusTimer)
      if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    }
  }, [refreshLaunchStatus])

  useEffect(() => {
    if (consoleMode !== 'ros') return
    const timer = window.setTimeout(() => void refreshRosGraph(), 0)
    return () => window.clearTimeout(timer)
  }, [consoleMode, refreshRosGraph])

  useEffect(() => {
    if (launchMode !== null) return
    launchReadyMode.current = null
    launchReadyStartedAt.current = 0
    launchReadyStableSamples.current = 0
  }, [launchMode])

  useEffect(() => {
    const pendingMode = launchReadyMode.current
    if (pendingMode === null || launchMode !== pendingMode) return
    if (lastMessageAt === null || lastMessageAt < launchReadyStartedAt.current) return

    const homeTarget = NAMED_TARGETS.home
    const reachedHome = robotInfo.arm_joints.every((joint) => {
      const current = currentJoints[joint]
      const target = homeTarget[joint]
      return (
        typeof current === 'number' &&
        typeof target === 'number' &&
        Math.abs(current - target) <= HOME_READY_TOLERANCE_RAD
      )
    })

    if (!reachedHome) {
      launchReadyStableSamples.current = 0
      return
    }

    launchReadyStableSamples.current += 1
    if (launchReadyStableSamples.current < HOME_READY_STABLE_SAMPLES) return

    const label = pendingMode === 'mock' ? '가상 하드웨어' : '실기기 하드웨어'
    appendEventLog('valid', `${label} ready: home position reached`)
    launchReadyMode.current = null
    launchReadyStartedAt.current = 0
    launchReadyStableSamples.current = 0
  }, [appendEventLog, currentJoints, lastMessageAt, launchMode, robotInfo.arm_joints])

  const setJointTarget = useCallback((joint: string, value: number) => {
    targetTouched.current = true
    setTargetPreviewActive(true)
    setActivePlanId(null)
    setTrajectorySummary(null)
    setConsoleStatus('idle', 'Target changed')
    setTargetJoints((previous) => ({ ...previous, [joint]: value }))
  }, [setConsoleStatus])

  const startDegreeEdit = useCallback((joint: string, value: number) => {
    setEditingDegreeJoint(joint)
    setDegreeDraft(Number.isFinite(value) ? radToDeg(value).toFixed(1) : '')
  }, [])

  const commitDegreeEdit = useCallback(() => {
    if (!editingDegreeJoint) return
    const parsed = Number(degreeDraft.trim())
    if (!Number.isFinite(parsed)) {
      setConsoleStatus('error', `${editingDegreeJoint} degree input is invalid`)
      return
    }

    const radians = degToRad(parsed)
    setJointTarget(editingDegreeJoint, radians)
    const limit = robotInfo.limits.joints[editingDegreeJoint]
    if (
      limit &&
      ((typeof limit.lower === 'number' && radians < limit.lower) ||
        (typeof limit.upper === 'number' && radians > limit.upper))
    ) {
      setConsoleStatus('error', `${editingDegreeJoint} target violates joint limit`)
    }
    setEditingDegreeJoint(null)
    setDegreeDraft('')
  }, [degreeDraft, editingDegreeJoint, robotInfo.limits.joints, setConsoleStatus, setJointTarget])

  const cancelDegreeEdit = useCallback(() => {
    setEditingDegreeJoint(null)
    setDegreeDraft('')
  }, [])

  const executeGripperTarget = useCallback(
    async (position: number) => {
      try {
        const response = await fetch(`${API_BASE}/motion/gripper`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ position, max_effort: 0 }),
        })
        await readMotionResponse(response)
        setConsoleStatus('idle', `Gripper command accepted (${position.toFixed(2)})`)
        return true
      } catch (error) {
        setConsoleStatus(
          'error',
          `Gripper unavailable (${error instanceof Error ? error.message : 'failed'})`,
        )
        return false
      }
    },
    [setConsoleStatus],
  )

  const applyNamedTarget = useCallback((name: string) => {
    const alias = name === 'ready' || name === 'pre_grasp' ? 'home' : name
    const target = NAMED_TARGETS[alias]
    if (!target) return
    targetTouched.current = true
    setTargetPreviewActive(true)
    setActivePlanId(null)
    setTrajectorySummary(null)
    setConsoleStatus('idle', `${name} target loaded`)
    setTargetJoints((previous) => ({ ...previous, ...target }))
  }, [setConsoleStatus])

  const resetTargetToCurrent = useCallback(() => {
    if (Object.keys(currentJoints).length === 0) {
      setConsoleStatus('error', 'Current joint state not available yet')
      return
    }
    targetTouched.current = true
    setTargetPreviewActive(false)
    setTargetJoints({ ...currentJoints })
    setActivePlanId(null)
    setTrajectorySummary(null)
    setConsoleStatus('idle', 'Current state copied')
  }, [currentJoints, setConsoleStatus])

  const validateTarget = useCallback(async () => {
    const missing = controlJoints.filter((joint) => typeof targetJoints[joint] !== 'number')
    if (missing.length > 0) {
      setConsoleStatus('error', `Missing ${missing.join(', ')}`)
      return
    }

    const outOfRange = controlJoints.filter((joint) => {
      const limit = robotInfo.limits.joints[joint]
      const value = targetJoints[joint]
      if (!limit || typeof value !== 'number') return false
      return (
        (typeof limit.lower === 'number' && value < limit.lower) ||
        (typeof limit.upper === 'number' && value > limit.upper)
      )
    })

    if (outOfRange.length > 0) {
      setConsoleStatus('error', `Out of range: ${outOfRange.join(', ')}`)
      return
    }

    const jointNames = robotInfo.arm_joints
    const positions = jointNames.map((joint) => targetJoints[joint])
    if (positions.some((value) => typeof value !== 'number')) {
      setConsoleStatus('error', 'Arm target incomplete')
      return
    }

    try {
      setMotionBusy(true)
      setConsoleStatus('idle', 'Plan validation requested')
      setActivePlanId(null)
      setTrajectorySummary(null)
      const response = await fetch(`${API_BASE}/motion/plan-joints`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          joint_names: jointNames,
          positions,
          velocity_scale: 0.3,
        }),
      })
      const data = await readMotionResponse(response)
      setActivePlanId(data.plan_id ?? null)
      if (typeof data.duration === 'number' || typeof data.point_count === 'number') {
        const duration = typeof data.duration === 'number' ? `${data.duration.toFixed(2)}s` : 'n/a'
        const points = typeof data.point_count === 'number' ? data.point_count : 0
        setTrajectorySummary(`${points} points, ${duration}`)
        appendEventLog('valid', `Trajectory ready (${points} points, ${duration})`)
      }
      setConsoleStatus('valid', data.message || 'Plan ready')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed'
      setConsoleStatus(
        'error',
        `Plan unavailable (${message})`,
      )
    } finally {
      setMotionBusy(false)
    }
  }, [
    appendEventLog,
    controlJoints,
    robotInfo.arm_joints,
    robotInfo.limits.joints,
    setConsoleStatus,
    targetJoints,
  ])

  const executeTarget = useCallback(async () => {
    if (!activePlanId) {
      setConsoleStatus('error', 'No valid plan. Press Plan first.')
      return
    }

    const jointNames = robotInfo.arm_joints
    const positions = jointNames.map((joint) => targetJoints[joint])
    if (positions.some((value) => typeof value !== 'number')) {
      setConsoleStatus('error', 'Arm target incomplete')
      return
    }

    try {
      setMotionBusy(true)
      setConsoleStatus('idle', 'Execute requested')
      const response = await fetch(`${API_BASE}/motion/execute-joints`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          joint_names: jointNames,
          positions,
          velocity_scale: 0.3,
          plan_id: activePlanId,
        }),
      })
      const data = await readMotionResponse(response)

      setTargetPreviewActive(false)
      setActivePlanId(null)
      setTrajectorySummary(null)

      const gripperTarget = targetJoints[robotInfo.gripper_command_joint]
      if (typeof gripperTarget === 'number') {
        await executeGripperTarget(gripperTarget)
      }

      setConsoleStatus('idle', data.message || 'Execute request completed')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed'
      setActivePlanId(null)
      setTrajectorySummary(null)
      setTargetPreviewActive(false)
      setConsoleStatus('error', `Execute unavailable (${message})`)
    } finally {
      setMotionBusy(false)
    }
  }, [
    activePlanId,
    executeGripperTarget,
    robotInfo.arm_joints,
    robotInfo.gripper_command_joint,
    setConsoleStatus,
    targetJoints,
  ])

  const stopRobot = useCallback(async () => {
    try {
      setMotionBusy(true)
      setConsoleStatus('idle', 'Stop requested')
      const response = await fetch(`${API_BASE}/motion/stop`, { method: 'POST' })
      const data = (await response.json()) as MotionResponse
      if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`)
      setConsoleStatus('idle', data.message || 'Stop completed')
    } catch (error) {
      setConsoleStatus(
        'error',
        `Stop unavailable (${error instanceof Error ? error.message : 'failed'})`,
      )
    } finally {
      setMotionBusy(false)
    }
  }, [setConsoleStatus])

  const showSystemNotice = useCallback((message: string) => {
    setSystemNotice(message)
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    noticeTimer.current = window.setTimeout(() => setSystemNotice(null), 3000)
  }, [])

  const stopHardwareMode = useCallback(
    async (mode: HardwareMode) => {
      const label = mode === 'mock' ? '가상 하드웨어' : '실기기 하드웨어'
      const confirmed = window.confirm(`${label} 연동을 종료하시겠습니까?`)
      if (!confirmed) return

      setLaunchBusy(true)
      appendEventLog('idle', `${label} launch stop requested`)
      launchReadyMode.current = null
      launchReadyStartedAt.current = 0
      launchReadyStableSamples.current = 0
      try {
        const response = await fetch(`${API_BASE}/robot/launch/stop`, { method: 'POST' })
        const data = (await response.json()) as LaunchResponse
        if (!response.ok || !data.ok) {
          appendEventLog('error', data.message || 'ROS launch stop failed')
          showSystemNotice(data.message || 'ROS launch를 종료하지 못했습니다.')
          return
        }

        setLaunchMode(null)
        setTargetPreviewActive(false)
        setActivePlanId(null)
        setTrajectorySummary(null)
        setConsoleStatus('idle', `${label} launch stopped`)
      } catch (error) {
        appendEventLog(
          'error',
          `Launch stop unavailable (${error instanceof Error ? error.message : 'failed'})`,
        )
        showSystemNotice(
          `백엔드 연결을 확인해주세요. ${error instanceof Error ? error.message : ''}`.trim(),
        )
      } finally {
        setLaunchBusy(false)
      }
    },
    [appendEventLog, setConsoleStatus, showSystemNotice],
  )

  const handleHardwareMode = useCallback(
    async (mode: HardwareMode) => {
      if (launchMode === mode) {
        await stopHardwareMode(mode)
        return
      }

      if (launchMode !== null) {
        return
      }

      const label = mode === 'mock' ? '가상 하드웨어' : '실기기 하드웨어'
      const confirmed = window.confirm(`${label}로 연동하시겠습니까?`)
      if (!confirmed) return

      setLaunchBusy(true)
      appendEventLog('idle', `${label} launch start requested`)
      try {
        const response = await fetch(`${API_BASE}/robot/launch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode }),
        })
        const data = (await response.json()) as LaunchResponse
        if (!response.ok || !data.ok) {
          if (mode === 'real' && data.code === 'hardware_disconnected') {
            appendEventLog('error', '실기기 연결을 확인해주세요.')
            showSystemNotice('실기기 연결을 확인해주세요.')
          } else {
            appendEventLog('error', data.message || 'ROS launch start failed')
            showSystemNotice(data.message || 'ROS launch를 시작하지 못했습니다.')
          }
          return
        }

        const startedMode = data.status?.mode ?? mode
        setLaunchMode(startedMode)
        launchReadyMode.current = startedMode
        launchReadyStartedAt.current = Date.now()
        launchReadyStableSamples.current = 0
        setConsoleStatus('idle', `${label} launch started`)
        appendEventLog('idle', `${label} waiting for home position`)
        refreshLaunchStatus()
      } catch (error) {
        appendEventLog(
          'error',
          `Launch start unavailable (${error instanceof Error ? error.message : 'failed'})`,
        )
        showSystemNotice(
          `백엔드 연결을 확인해주세요. ${error instanceof Error ? error.message : ''}`.trim(),
        )
      } finally {
        setLaunchBusy(false)
      }
    },
    [appendEventLog, launchMode, refreshLaunchStatus, setConsoleStatus, showSystemNotice, stopHardwareMode],
  )

  const rosAge = health?.ros?.last_joint_state_age_sec
  const rosLive = Boolean(health?.ros?.joint_states_seen && typeof rosAge === 'number' && rosAge < 3)
  const currentPreviewJoints = useMemo(
    () => withMimicGripper(currentJoints, robotInfo.gripper_command_joint),
    [currentJoints, robotInfo.gripper_command_joint],
  )
  const targetPreviewJoints = useMemo(
    () => withMimicGripper({ ...currentJoints, ...targetJoints }, robotInfo.gripper_command_joint),
    [currentJoints, robotInfo.gripper_command_joint, targetJoints],
  )
  const showTargetPreview = targetPreviewActive && Object.keys(targetJoints).length > 0

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            OMX
          </div>
          <div>
            <p className="eyebrow">ROS2 Web Control</p>
            <h1>OMX-F Console</h1>
          </div>
        </div>

        <div className="topbar-status" aria-label="connection status">
          <div className="launch-controls" aria-label="hardware launch controls">
            <button
              className={launchMode === 'mock' ? 'launch-button active' : 'launch-button'}
              type="button"
              disabled={launchBusy || (launchMode !== null && launchMode !== 'mock')}
              onClick={() => handleHardwareMode('mock')}
            >
              <Cpu size={15} />
              <span>가상 하드웨어</span>
            </button>
            <button
              className={launchMode === 'real' ? 'launch-button active' : 'launch-button'}
              type="button"
              disabled={launchBusy || (launchMode !== null && launchMode !== 'real')}
              onClick={() => handleHardwareMode('real')}
            >
              <Cable size={15} />
              <span>실기기 하드웨어</span>
            </button>
          </div>
          <StatusPill
            tone={connection === 'online' ? 'good' : connection === 'connecting' ? 'warn' : 'bad'}
            icon={connection === 'online' ? <Wifi size={15} /> : <WifiOff size={15} />}
            label={connection === 'online' ? 'WebSocket online' : connection}
          />
          <StatusPill
            tone={rosLive ? 'good' : 'warn'}
            icon={<Radio size={15} />}
            label={rosLive ? '/joint_states live' : 'waiting for ROS'}
          />
        </div>
      </header>
      {systemNotice && (
        <div className="system-notice-backdrop" role="alert" aria-live="assertive">
          <div className="system-notice">
            <AlertTriangle size={22} />
            <strong>{systemNotice}</strong>
          </div>
        </div>
      )}

      <section className="workspace">
        <aside className="control-panel">
          <section className="panel-section mode-section" aria-label="console mode">
            <div className="mode-toggle" role="radiogroup" aria-label="control mode">
              <button
                className={consoleMode === 'joints' ? 'mode-option active' : 'mode-option'}
                type="button"
                role="radio"
                aria-checked={consoleMode === 'joints'}
                onClick={() => setConsoleMode('joints')}
              >
                <Route size={16} />
                <span>Joint Targets</span>
              </button>
              <button
                className={consoleMode === 'ros' ? 'mode-option active' : 'mode-option'}
                type="button"
                role="radio"
                aria-checked={consoleMode === 'ros'}
                onClick={() => setConsoleMode('ros')}
              >
                <ListTree size={16} />
                <span>Topic·Service·Action</span>
              </button>
            </div>
          </section>

          {consoleMode === 'joints' ? (
            <>
          <section className="panel-section joint-target-section">
            <div className="section-title">
              <h2>Joint Targets</h2>
              <button className="icon-button" type="button" onClick={resetTargetToCurrent} title="Copy current">
                <RotateCcw size={17} />
              </button>
            </div>

            <div className="joint-list">
              {controlJoints.map((joint) => {
                const limit = robotInfo.limits.joints[joint] ?? {}
                const min = limit.lower ?? -Math.PI * 2
                const max = limit.upper ?? Math.PI * 2
                const current = currentJoints[joint]
                const target = targetJoints[joint] ?? current ?? 0
                const delta =
                  typeof current === 'number' && typeof target === 'number' ? target - current : 0

                return (
                  <div className="joint-row" key={joint}>
                    <span className="joint-meta">
                      <span className="joint-name">{joint}</span>
                      <span className="joint-readout">
                        <span>{formatRad(current)}</span>
                        <span>{formatRad(target)}</span>
                        <span className={Math.abs(delta) > 0.02 ? 'delta hot' : 'delta'}>
                          {delta >= 0 ? '+' : ''}
                          {delta.toFixed(2)}
                        </span>
                      </span>
                    </span>
                    <input
                      type="range"
                      aria-label={`${joint} target`}
                      min={min}
                      max={max}
                      step={0.01}
                      value={target}
                      onChange={(event) => setJointTarget(joint, Number(event.currentTarget.value))}
                      style={{
                        ['--val' as string]: max > min
                          ? Math.min(1, Math.max(0, (target - min) / (max - min)))
                          : 0,
                      }}
                    />
                    <span className="degree-row">
                      <span>{formatDeg(current)}</span>
                      {editingDegreeJoint === joint ? (
                        <input
                          className="degree-input"
                          type="text"
                          inputMode="decimal"
                          value={degreeDraft}
                          autoFocus
                          onFocus={(event) => event.currentTarget.select()}
                          onChange={(event) => {
                            const val = event.currentTarget.value
                            if (/^-?\d*\.?\d*$/.test(val)) setDegreeDraft(val)
                          }}
                          onBlur={commitDegreeEdit}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') commitDegreeEdit()
                            if (event.key === 'Escape') cancelDegreeEdit()
                          }}
                        />
                      ) : (
                        <button
                          className="degree-value"
                          type="button"
                          title="더블클릭하여 목표 각도 직접 입력"
                          onDoubleClick={() => startDegreeEdit(joint, target)}
                        >
                          {formatDeg(target)}
                        </button>
                      )}
                    </span>
                  </div>
                )
              })}
            </div>
          </section>

          <section className="panel-section command-section">
            <div className="named-actions">
              {ACTION_NAMES.map((name) => (
                <button
                  className="command-button"
                  type="button"
                  onClick={() => applyNamedTarget(name)}
                  key={name}
                >
                  {name === 'home' && <Home size={16} />}
                  {name === 'init' && <Square size={16} />}
                  {name === 'open' && <DoorOpen size={16} />}
                  {name === 'close' && <Hand size={16} />}
                  <span>{name}</span>
                </button>
              ))}
            </div>

            <div className="execution-row">
              <button className="plan-button" type="button" disabled={motionBusy} onClick={validateTarget}>
                <Route size={17} />
                <span>Plan</span>
              </button>
              <button
                className="execute-button"
                type="button"
                disabled={planState !== 'valid' || !activePlanId || motionBusy}
                onClick={executeTarget}
              >
                <Play size={17} />
                <span>Execute</span>
              </button>
              <button className="stop-button" type="button" onClick={stopRobot}>
                <Pause size={17} />
                <span>Stop</span>
              </button>
            </div>

            {trajectorySummary && (
              <div className="trajectory-section">
                <span>Trajectory</span>
                <strong>{trajectorySummary}</strong>
              </div>
            )}

          </section>
            </>
          ) : (
            <RosInterfacePanel
              graph={rosGraph}
              graphBusy={rosGraphBusy}
              graphError={rosGraphError}
              kind={rosKind}
              selectedName={selectedRosName}
              domainDraft={rosDomainDraft}
              requestDraft={rosRequestDraft}
              commandBusy={rosCommandBusy}
              commandOutput={rosCommandOutput}
              onKindChange={handleRosKindChange}
              onSelectName={handleRosSelectName}
              onDomainDraftChange={setRosDomainDraft}
              onRequestDraftChange={handleRosRequestDraftChange}
              onRefresh={refreshRosGraph}
              onSaveDomain={saveRosDomain}
              onSend={sendRosCommand}
            />
          )}

          <section className="panel-section event-log-section" aria-label="event log">
            <div className="section-title">
              <h2>Event Log</h2>
              <div className="event-log-actions">
                <span className="log-count">{eventLogs.length}</span>
                <button
                  className="icon-button"
                  type="button"
                  onClick={resetEventLogs}
                  disabled={eventLogs.length === 0}
                  title="Reset event log"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            <div className="event-log-list" ref={eventLogListRef}>
              {eventLogs.map((log) => (
                <div className={`event-log-row ${log.state}`} key={log.id}>
                  <span className="event-log-time">{log.at}</span>
                  <span className="event-log-state">{log.state}</span>
                  <span className="event-log-message">{log.message}</span>
                </div>
              ))}
            </div>
          </section>
        </aside>

        <section className="viewer-panel">
          <div className="viewer-header">
            <div>
              <p className="eyebrow">Unity WebGL View</p>
              <h2>omx_f Preview</h2>
            </div>
            <StatusPill
              tone={showTargetPreview ? 'warn' : 'good'}
              icon={<Square size={15} />}
              label={showTargetPreview ? 'target preview' : 'current only'}
            />
          </div>

          <UnityWebGLView
            currentJoints={currentPreviewJoints}
            targetJoints={targetPreviewJoints}
            showTargetPreview={showTargetPreview}
          />

          <div className="telemetry-strip">
            {controlJoints.map((joint) => (
              <div className="telemetry-cell" key={joint}>
                <span>{joint}</span>
                <strong>{formatRad(currentJoints[joint])}</strong>
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  )
}

function StatusPill({
  tone,
  icon,
  label,
}: {
  tone: 'good' | 'warn' | 'bad'
  icon: ReactNode
  label: string
}) {
  return (
    <span className={`status-pill ${tone}`}>
      {icon}
      <span>{label}</span>
    </span>
  )
}

function RosInterfacePanel({
  graph,
  graphBusy,
  graphError,
  kind,
  selectedName,
  domainDraft,
  requestDraft,
  commandBusy,
  commandOutput,
  onKindChange,
  onSelectName,
  onDomainDraftChange,
  onRequestDraftChange,
  onRefresh,
  onSaveDomain,
  onSend,
}: {
  graph: RosGraphResponse | null
  graphBusy: boolean
  graphError: string | null
  kind: RosResourceKind
  selectedName: string | null
  domainDraft: string
  requestDraft: string
  commandBusy: boolean
  commandOutput: string | null
  onKindChange: (kind: RosResourceKind) => void
  onSelectName: (name: string) => void
  onDomainDraftChange: (value: string) => void
  onRequestDraftChange: (value: string) => void
  onRefresh: () => void
  onSaveDomain: () => void
  onSend: () => void
}) {
  const resources = graph?.[kind] ?? []
  const [resourceSearch, setResourceSearch] = useState('')
  const normalizedSearch = resourceSearch.trim().toLowerCase()
  const filteredResources = normalizedSearch
    ? resources.filter((entry) =>
        [entry.name, ...entry.types].some((value) => value.toLowerCase().includes(normalizedSearch)),
      )
    : resources
  const selected =
    filteredResources.find((entry) => entry.name === selectedName) ??
    (normalizedSearch ? null : filteredResources[0] ?? null)
  const selectedType = selected?.types[0] ?? ''
  const actionLabel = kind === 'topics' ? 'Select' : kind === 'services' ? 'Call Service' : 'Send Goal'
  const imageCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const [imageStatus, setImageStatus] = useState('Select an image topic.')

  useEffect(() => {
    setResourceSearch('')
  }, [kind])

  useEffect(() => {
    if (kind !== 'topics' || !selected?.name || !selectedType) {
      return
    }

    let socket: WebSocket | null = null
    let disposed = false

    const drawFrame = (frame: RosImageFrame) => {
      const canvas = imageCanvasRef.current
      const context = canvas?.getContext('2d')
      if (!canvas || !context) return

      if (frame.data_url) {
        const image = new Image()
        image.onload = () => {
          canvas.width = image.naturalWidth || 640
          canvas.height = image.naturalHeight || 480
          context.drawImage(image, 0, 0, canvas.width, canvas.height)
          setImageStatus(`${canvas.width}x${canvas.height} compressed`)
        }
        image.src = frame.data_url
        return
      }

      if (!frame.data || !frame.width || !frame.height) return
      const raw = Uint8Array.from(atob(frame.data), (char) => char.charCodeAt(0))
      const imageData = context.createImageData(frame.width, frame.height)
      const encoding = (frame.encoding ?? '').toLowerCase()
      const isYuyv422 =
        encoding.includes('yuy') || encoding.includes('yuv422') || encoding.includes('yuy422')
      const isUyvy422 = encoding.includes('uyvy')
      const channels =
        isYuyv422 || isUyvy422
          ? 2
          : encoding.includes('rgba') || encoding.includes('bgra')
            ? 4
            : encoding.includes('mono')
              ? 1
              : 3
      const step = frame.step ?? frame.width * channels

      for (let y = 0; y < frame.height; y += 1) {
        if (isYuyv422 || isUyvy422) {
          for (let x = 0; x < frame.width; x += 2) {
            const src = y * step + x * 2
            const y0 = raw[src + (isUyvy422 ? 1 : 0)] ?? 0
            const u = raw[src + (isUyvy422 ? 0 : 1)] ?? 128
            const y1 = raw[src + (isUyvy422 ? 3 : 2)] ?? y0
            const v = raw[src + (isUyvy422 ? 2 : 3)] ?? 128
            const rgb0 = yuvToRgb(y0, u, v)
            const rgb1 = yuvToRgb(y1, u, v)
            const dst0 = (y * frame.width + x) * 4
            imageData.data[dst0] = rgb0.r
            imageData.data[dst0 + 1] = rgb0.g
            imageData.data[dst0 + 2] = rgb0.b
            imageData.data[dst0 + 3] = 255
            if (x + 1 < frame.width) {
              const dst1 = (y * frame.width + x + 1) * 4
              imageData.data[dst1] = rgb1.r
              imageData.data[dst1 + 1] = rgb1.g
              imageData.data[dst1 + 2] = rgb1.b
              imageData.data[dst1 + 3] = 255
            }
          }
          continue
        }

        for (let x = 0; x < frame.width; x += 1) {
          const src = y * step + x * channels
          const dst = (y * frame.width + x) * 4
          if (encoding.includes('mono')) {
            const value = raw[src] ?? 0
            imageData.data[dst] = value
            imageData.data[dst + 1] = value
            imageData.data[dst + 2] = value
            imageData.data[dst + 3] = 255
          } else {
            const bgr = encoding.includes('bgr')
            imageData.data[dst] = raw[src + (bgr ? 2 : 0)] ?? 0
            imageData.data[dst + 1] = raw[src + 1] ?? 0
            imageData.data[dst + 2] = raw[src + (bgr ? 0 : 2)] ?? 0
            imageData.data[dst + 3] = channels === 4 ? raw[src + 3] ?? 255 : 255
          }
        }
      }

      canvas.width = frame.width
      canvas.height = frame.height
      context.putImageData(imageData, 0, 0)
      setImageStatus(`${frame.width}x${frame.height} ${frame.encoding ?? 'raw'}`)
    }

    socket = new WebSocket(
      `${WS_BASE}/ws/image?topic=${encodeURIComponent(selected.name)}&type=${encodeURIComponent(selectedType)}`,
    )
    socket.onopen = () => setImageStatus('Waiting for image frames...')
    socket.onerror = () => setImageStatus('Image stream connection failed.')
    socket.onclose = () => {
      if (!disposed) setImageStatus('Image stream closed.')
    }
    socket.onmessage = (event) => {
      const frame = JSON.parse(event.data) as RosImageFrame
      if (frame.type === 'image_error') {
        setImageStatus(frame.message ?? 'Image stream failed.')
        return
      }
      drawFrame(frame)
    }

    return () => {
      disposed = true
      socket?.close()
    }
  }, [kind, selected?.name, selectedType])

  return (
    <section className="panel-section ros-panel" aria-label="topic service action browser">
      <div className="section-title">
        <h2>Topic·Service·Action</h2>
        <button className="icon-button" type="button" onClick={onRefresh} disabled={graphBusy} title="Refresh ROS graph">
          <RefreshCw size={17} />
        </button>
      </div>

      <div className="ros-domain-row">
        <label htmlFor="ros-domain-id">ROS_DOMAIN_ID</label>
        <input
          id="ros-domain-id"
          className="ros-domain-input"
          type="text"
          inputMode="numeric"
          value={domainDraft}
          placeholder="default"
          onChange={(event) => onDomainDraftChange(event.currentTarget.value)}
        />
        <button className="ros-small-button" type="button" onClick={onSaveDomain} disabled={commandBusy}>
          <Check size={15} />
          <span>Apply</span>
        </button>
      </div>

      <div className="ros-kind-tabs" role="tablist" aria-label="ROS resource type">
        {(['topics', 'services', 'actions'] as const).map((item) => (
          <button
            key={item}
            className={kind === item ? 'ros-kind-tab active' : 'ros-kind-tab'}
            type="button"
            role="tab"
            aria-selected={kind === item}
            onClick={() => onKindChange(item)}
          >
            {item === 'topics' && 'Topic'}
            {item === 'services' && 'Service'}
            {item === 'actions' && 'Action'}
            <span>{graph?.[item]?.length ?? 0}</span>
          </button>
        ))}
      </div>

      {graphError && <div className="ros-error">{graphError}</div>}

      <div className="ros-workbench">
        <div className="ros-resource-list" aria-label={`${kind} list`}>
          <label className="ros-search-field" htmlFor="ros-resource-search">
            <Search size={14} />
            <input
              id="ros-resource-search"
              type="search"
              value={resourceSearch}
              placeholder={`Search ${kind}`}
              onChange={(event) => setResourceSearch(event.currentTarget.value)}
            />
          </label>
          {graphBusy && <div className="ros-empty">Loading ROS graph...</div>}
          {!graphBusy && resources.length === 0 && (
            <div className="ros-empty">
              {kind === 'topics' ? 'No image topics discovered.' : `No ${kind} discovered.`}
            </div>
          )}
          {!graphBusy && resources.length > 0 && filteredResources.length === 0 && (
            <div className="ros-empty">No matching {kind}.</div>
          )}
          {!graphBusy &&
            filteredResources.map((entry) => (
              <button
                key={`${entry.name}-${entry.types.join('|')}`}
                className={selected?.name === entry.name ? 'ros-resource active' : 'ros-resource'}
                type="button"
                onClick={() => onSelectName(entry.name)}
              >
                <strong>{entry.name}</strong>
                <span>{entry.types[0] ?? 'unknown type'}</span>
              </button>
            ))}
        </div>

        <div className={kind === 'topics' ? 'ros-inspector topic-inspector' : 'ros-inspector command-inspector'}>
          <div className="ros-selected-meta">
            <span>{kind.slice(0, -1)}</span>
            <strong>{selected?.name ?? 'none'}</strong>
            <code>{selectedType || 'no type'}</code>
          </div>

          {kind === 'topics' ? (
            <div className="image-topic-preview">
              <canvas ref={imageCanvasRef} className="image-topic-canvas" />
              <span>{imageStatus}</span>
            </div>
          ) : (
            <>
              <label className="ros-json-label" htmlFor="ros-request-json">
                JSON {kind === 'services' ? 'request' : 'goal'}
              </label>
              <textarea
                id="ros-request-json"
                className="ros-json-input"
                spellCheck={false}
                value={requestDraft}
                onChange={(event) => onRequestDraftChange(event.currentTarget.value)}
              />
            </>
          )}

          <button
            className="ros-send-button"
            type="button"
            disabled={!selected || commandBusy}
            onClick={onSend}
          >
            {kind === 'topics' ? <Braces size={17} /> : <Send size={17} />}
            <span>{actionLabel}</span>
          </button>

          <pre className="ros-output">{commandOutput ?? 'No response yet.'}</pre>
        </div>
      </div>
    </section>
  )
}

declare global {
  interface Window {
    createUnityInstance?: (
      canvas: HTMLCanvasElement,
      config: Record<string, unknown>,
      onProgress?: (progress: number) => void,
    ) => Promise<{ SendMessage: (objectName: string, methodName: string, value: string) => void; Quit: () => Promise<void> }>
  }
}

function UnityWebGLView({
  currentJoints,
  targetJoints,
  showTargetPreview,
}: {
  currentJoints: JointMap
  targetJoints: JointMap
  showTargetPreview: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const unityRef = useRef<{ SendMessage: (objectName: string, methodName: string, value: string) => void; Quit: () => Promise<void> } | null>(null)
  const [status, setStatus] = useState<'checking' | 'missing' | 'loading' | 'ready' | 'error'>('checking')
  const [progress, setProgress] = useState(0)
  const latestCurrentJoints = useRef<JointMap>({})
  const latestTargetJoints = useRef<JointMap>({})
  const latestShowTargetPreview = useRef(false)
  const manifestUrl = '/unity-webgl/manifest.json'

  useEffect(() => {
    latestCurrentJoints.current = currentJoints
    if (unityRef.current && Object.keys(currentJoints).length > 0) {
      unityRef.current.SendMessage(
        'OmxWebJointBridge',
        'SetCurrentJointStateJson',
        JSON.stringify({ type: 'current_joint_state', joints: currentJoints }),
      )
    }
  }, [currentJoints])

  useEffect(() => {
    latestTargetJoints.current = targetJoints
    latestShowTargetPreview.current = showTargetPreview
    if (unityRef.current) {
      unityRef.current.SendMessage(
        'OmxWebJointBridge',
        'SetTargetPreviewVisible',
        showTargetPreview ? 'true' : 'false',
      )
      unityRef.current.SendMessage(
        'OmxWebJointBridge',
        'SetTargetJointStateJson',
        JSON.stringify({ type: 'target_joint_state', joints: targetJoints }),
      )
    }
  }, [showTargetPreview, targetJoints])

  useEffect(() => {
    let disposed = false
    let script: HTMLScriptElement | null = null

    // Unity WebGL's loader installs a capture-phase keyboard handler that calls
    // preventDefault() on most keys so the canvas can drive input. That blocks
    // character insertion into any focused <input>/<textarea>. Neutralize the
    // event's preventDefault for form-field targets — Unity's listener still
    // runs and the event still reaches React handlers, but the browser's
    // default character-insertion is no longer suppressed.
    const noopPreventDefault = () => {}
    const guardKeyboardForFormFields = (event: Event) => {
      const target = document.activeElement as HTMLElement | null
      if (!target) return
      const tag = target.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) {
        Object.defineProperty(event, 'preventDefault', {
          configurable: true,
          value: noopPreventDefault,
        })
      }
    }
    window.addEventListener('keydown', guardKeyboardForFormFields, true)
    window.addEventListener('keypress', guardKeyboardForFormFields, true)
    window.addEventListener('keyup', guardKeyboardForFormFields, true)

    const boot = async () => {
      try {
        const response = await fetch(manifestUrl)
        if (!response.ok) {
          setStatus('missing')
          return
        }
        const manifest = (await response.json()) as UnityBuildManifest
        if (!manifest.available) {
          setStatus('missing')
          return
        }

        setStatus('loading')
        script = document.createElement('script')
        script.src = manifest.loaderUrl
        script.async = true
        script.onload = async () => {
          if (disposed || !canvasRef.current || !window.createUnityInstance) return
          try {
            const instance = await window.createUnityInstance(
              canvasRef.current,
              {
                dataUrl: manifest.dataUrl,
                frameworkUrl: manifest.frameworkUrl,
                codeUrl: manifest.codeUrl,
                streamingAssetsUrl: '/unity-webgl/StreamingAssets',
                companyName: 'OMX',
                productName: 'OMX-F Web Preview',
                productVersion: '0.1.0',
              },
              (value) => setProgress(value),
            )
            if (disposed) {
              await instance.Quit()
              return
            }
            unityRef.current = instance
            setStatus('ready')
            if (Object.keys(latestCurrentJoints.current).length > 0) {
              instance.SendMessage(
                'OmxWebJointBridge',
                'SetCurrentJointStateJson',
                JSON.stringify({ type: 'current_joint_state', joints: latestCurrentJoints.current }),
              )
            }
            instance.SendMessage(
              'OmxWebJointBridge',
              'SetTargetPreviewVisible',
              latestShowTargetPreview.current ? 'true' : 'false',
            )
            instance.SendMessage(
              'OmxWebJointBridge',
              'SetTargetJointStateJson',
              JSON.stringify({ type: 'target_joint_state', joints: latestTargetJoints.current }),
            )
          } catch (error) {
            console.error(error)
            setStatus('error')
          }
        }
        script.onerror = () => setStatus('error')
        document.body.appendChild(script)
      } catch {
        setStatus('missing')
      }
    }

    boot()

    return () => {
      disposed = true
      window.removeEventListener('keydown', guardKeyboardForFormFields, true)
      window.removeEventListener('keypress', guardKeyboardForFormFields, true)
      window.removeEventListener('keyup', guardKeyboardForFormFields, true)
      if (script?.parentNode) {
        script.parentNode.removeChild(script)
      }
      if (unityRef.current) {
        void unityRef.current.Quit()
        unityRef.current = null
      }
    }
  }, [])

  return (
    <div className="unity-stage" aria-label="Unity WebGL robot preview">
      <canvas id="omx-unity-canvas" ref={canvasRef} className={status === 'ready' ? 'unity-canvas ready' : 'unity-canvas'} />
      {status !== 'ready' && (
        <div className="unity-overlay">
          <strong>
            {status === 'checking' && 'Checking Unity WebGL build'}
            {status === 'missing' && 'Unity WebGL build not installed'}
            {status === 'loading' && `Loading Unity ${Math.round(progress * 100)}%`}
            {status === 'error' && 'Unity WebGL failed to load'}
          </strong>
          <span>
            {status === 'missing'
              ? 'Build OMX_AI.unity for WebGL, then sync it into public/unity-webgl.'
              : 'The canvas will receive joint_state messages through OmxWebJointBridge.'}
          </span>
        </div>
      )}
    </div>
  )
}

export default OmxConsole
