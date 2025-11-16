import {
  Float,
  Grid,
  Html,
  OrbitControls,
  QuadraticBezierLine,
  Sparkles,
} from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import type { FC } from "react";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { PumpStatus } from "../hooks/system";
import { isBoosterPump } from "../constants/pumps";

interface PumpVisual {
  id: string;
  state?: string;
  frequency: number;
  power: number;
  health: PumpHealth;
  color: string;
  accent: string;
  size: PumpSize;
}

interface WastewaterUnitVisual {
  id: string;
  loadFactor: number;
  color: string;
  position: [number, number, number];
}

interface System3DSceneProps {
  pumps?: PumpStatus[];
  inflow?: number;
  outflow?: number;
  tunnelFillRatio?: number;
  tunnelLevelL1?: number; // L1 level in meters
  tunnelLevelL2?: number; // L2 level in meters
  loading?: boolean;
}

type PumpHealth = "active" | "idle" | "fault";
type PumpSize = "small" | "large";
const BOOSTER_ACCENT = "#fbbf24";

const classifyState = (state?: string): PumpHealth => {
  if (!state) return "idle";
  const normalized = state.toLowerCase();
  if (normalized.includes("fault") || normalized.includes("alarm")) {
    return "fault";
  }
  if (
    normalized.includes("run") ||
    normalized.includes("on") ||
    normalized.includes("active")
  ) {
    return "active";
  }
  return "idle";
};

const pumpPalette: Record<PumpHealth, string> = {
  active: "#22d3ee",
  idle: "#475569",
  fault: "#fb7185",
};

const pumpAccentPalette: Record<PumpHealth, string> = {
  active: "#2dd4bf",
  idle: "#94a3b8",
  fault: "#fda4af",
};

const clamp01 = (value?: number) => {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
};

const getNow = () =>
  typeof performance !== "undefined" ? performance.now() : Date.now();

const getPumpSize = (id?: string): PumpSize =>
  isBoosterPump(id) ? "small" : "large";
interface PumpNodeProps {
  pump: PumpVisual;
  position: [number, number, number];
  index: number;
}

const PumpNode: FC<PumpNodeProps> = ({ pump, position, index }) => {
  const columnRef =
    useRef<THREE.Mesh<THREE.CylinderGeometry, THREE.MeshStandardMaterial>>(
      null
    );
  const beaconRef =
    useRef<THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>>(null);
  const rotationRef = useRef<THREE.Group>(null);
  const frequencyIndicatorRef = useRef<THREE.Mesh>(null);

  useFrame(() => {
    if (!columnRef.current || !beaconRef.current) return;
    const now = getNow();
    const time = now * 0.001;
    
    // Enhanced wobble based on frequency (0-50 Hz mapped to animation speed)
    const frequencyFactor = Math.min(pump.frequency / 50, 1);
    const wobble =
      pump.health === "active"
        ? 1 + Math.sin((time * 2 + index * 0.5) * (1 + frequencyFactor * 2)) * 0.12 * frequencyFactor
        : 1;
    columnRef.current.scale.y = THREE.MathUtils.lerp(
      columnRef.current.scale.y,
      wobble,
      0.12
    );
    
    // Rotate pump when active (based on frequency)
    if (rotationRef.current && pump.health === "active") {
      rotationRef.current.rotation.y = time * frequencyFactor * 0.5;
    }
    
    // Pulsing beacon with frequency-based intensity
    const beaconIntensity = pump.health === "active" ? 0.85 + Math.sin(time * 3) * 0.15 : 0.25;
    const beaconMaterial = beaconRef.current.material;
    beaconMaterial.opacity = THREE.MathUtils.lerp(
      beaconMaterial.opacity,
      beaconIntensity,
      0.15
    );
    
    // Frequency indicator (ring that scales with frequency)
    if (frequencyIndicatorRef.current && pump.health === "active") {
      const scale = 1 + (pump.frequency / 50) * 0.3;
      frequencyIndicatorRef.current.scale.setScalar(
        THREE.MathUtils.lerp(frequencyIndicatorRef.current.scale.x, scale, 0.1)
      );
    }
  });

  const radius = pump.size === "small" ? 0.26 : 0.35;
  const towerHeight = pump.size === "small" ? 0.9 : 1.25;
  const beaconSize = pump.size === "small" ? 0.14 : 0.18;

  return (
    <group position={position}>
      {/* Base ring with enhanced glow */}
      <mesh position={[0, -0.4, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[radius + 0.1, radius + 0.45, 48]} />
        <meshStandardMaterial
          color={pump.accent}
          emissive={pump.accent}
          emissiveIntensity={pump.health === "active" ? 0.4 : 0.15}
          opacity={0.75}
          transparent
        />
      </mesh>
      
      {/* Frequency indicator ring (scales with frequency) */}
      {pump.health === "active" && (
        <mesh ref={frequencyIndicatorRef} position={[0, -0.4, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[radius + 0.5, radius + 0.55, 32]} />
          <meshStandardMaterial
            color={pump.accent}
            emissive={pump.accent}
            emissiveIntensity={0.3}
            opacity={0.4}
            transparent
          />
        </mesh>
      )}
      
      <mesh position={[0, -0.15, 0]}>
        <cylinderGeometry args={[radius + 0.08, radius + 0.08, 0.2, 24]} />
        <meshStandardMaterial color="#0f172a" roughness={0.6} metalness={0.1} />
      </mesh>
      
      {/* Rotating pump group */}
      <group ref={rotationRef}>
        <mesh ref={columnRef} position={[0, towerHeight / 2, 0]} castShadow>
          <cylinderGeometry args={[radius, radius, towerHeight, 32]} />
          {pump.size === "small" && (
            <mesh position={[0, towerHeight * 0.4, 0]} castShadow>
              <torusGeometry args={[radius + 0.05, 0.04, 12, 48]} />
              <meshStandardMaterial
                color={BOOSTER_ACCENT}
                emissive={BOOSTER_ACCENT}
                emissiveIntensity={0.8}
                metalness={0.4}
              />
            </mesh>
          )}
          <meshStandardMaterial
            color={pump.color}
            emissive={pump.health === "active" ? pump.color : "#0f172a"}
            emissiveIntensity={pump.health === "active" ? 0.7 : 0.15}
            roughness={0.2}
            metalness={0.4}
          />
        </mesh>
      </group>
      
      {/* Enhanced beacon with power-based glow */}
      <mesh ref={beaconRef} position={[0, towerHeight + 0.35, 0]}>
        <sphereGeometry args={[beaconSize, 16, 16]} />
        <meshBasicMaterial 
          color={pump.accent} 
          opacity={pump.health === "active" ? 0.7 : 0.3} 
          transparent 
        />
      </mesh>
      
      {/* Power indicator (small particles around active pumps) */}
      {pump.health === "active" && pump.power > 0 && (
        <Sparkles
          count={Math.floor(pump.power / 50)}
          size={1.5}
          scale={[radius * 2, towerHeight * 0.5, radius * 2]}
          position={[0, towerHeight * 0.5, 0]}
          speed={0.3 + (pump.frequency / 50) * 0.5}
          color={pump.accent}
        />
      )}
      
      <Html center distanceFactor={18} position={[0, 1.8, 0]}>
        <div className="rounded-full border border-white/10 bg-slate-900/80 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-100 shadow-lg">
          {pump.id}
          {pump.health === "active" && (
            <span className="ml-1.5 text-[9px] text-slate-400">
              {pump.frequency.toFixed(0)}Hz
            </span>
          )}
        </div>
      </Html>
    </group>
  );
};

const TunnelLevelIndicator: FC<{ unit: WastewaterUnitVisual; level?: number }> = ({ unit, level = 0 }) => {
  // Scale based on level
  // For L1: 0-8m range, for L2: always 30m (show at max)
  const isL2 = unit.id === "L2";
  const normalizedLevel = isL2 ? 1.0 : clamp01(level / 8.0);
  const height = 0.6 + normalizedLevel * 0.8;
  const intensity = 0.3 + normalizedLevel * 0.7;
  
  return (
    <Float
      floatIntensity={0.2 + normalizedLevel * 0.3}
      speed={0.6 + normalizedLevel * 0.4}
    >
      <group position={unit.position}>
        {/* Base platform */}
        <mesh position={[0, -0.3, 0]} castShadow>
          <cylinderGeometry args={[0.5, 0.5, 0.1, 16]} />
          <meshStandardMaterial color="#1e293b" metalness={0.3} roughness={0.4} />
        </mesh>
        
        {/* Level indicator column */}
        <mesh position={[0, height / 2 - 0.3, 0]} castShadow>
          <cylinderGeometry args={[0.4, 0.4, height, 16]} />
          <meshStandardMaterial
            color={unit.color}
            emissive={unit.color}
            emissiveIntensity={intensity}
            metalness={0.3}
            roughness={0.2}
          />
        </mesh>
        
        {/* Top indicator */}
        <mesh position={[0, height - 0.3, 0]} castShadow>
          <sphereGeometry args={[0.25, 16, 16]} />
          <meshStandardMaterial
            color={unit.color}
            emissive={unit.color}
            emissiveIntensity={intensity * 1.5}
            metalness={0.4}
            roughness={0.15}
          />
        </mesh>
        
        <Html center distanceFactor={18} position={[0, height + 0.5, 0]}>
          <div className="rounded-full border border-white/10 bg-slate-900/80 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-blue-50 shadow-lg">
            <div className="text-center">
              <div className="text-xs font-bold">{unit.id}</div>
              <div className="text-[9px] text-slate-300 mt-0.5">
                {level.toFixed(2)} m
              </div>
            </div>
          </div>
        </Html>
      </group>
    </Float>
  );
};

const ChannelBase: FC<{ length: number; width: number }> = ({
  length,
  width,
}) => (
  <mesh position={[0, -0.45, 0]} receiveShadow>
    <boxGeometry args={[length, 0.2, width + 3]} />
    <meshStandardMaterial color="#020b17" roughness={0.7} metalness={0.05} />
  </mesh>
);

const TunnelWater: FC<{ ratio: number; length: number; width: number }> = ({
  ratio,
  length,
  width,
}) => {
  const height = 0.9 * clamp01(ratio);
  return (
    <mesh position={[0, -0.1 + height / 2, 0]}>
      <boxGeometry args={[length - 0.4, height, width - 0.2]} />
      <meshPhysicalMaterial
        color="#22d3ee"
        transparent
        opacity={0.25 + clamp01(ratio) * 0.35}
        roughness={0.15}
        metalness={0.1}
        transmission={0.3}
      />
    </mesh>
  );
};

const FlowPulse: FC<{
  start: [number, number, number];
  end: [number, number, number];
  color: string;
  speed?: number;
  offset?: number;
}> = ({ start, end, color, speed = 0.4, offset = 0 }) => {
  const ref = useRef<THREE.Mesh>(null);
  const startVec = useMemo(() => new THREE.Vector3(...start), [start]);
  const deltaVec = useMemo(
    () => new THREE.Vector3(...end).sub(startVec),
    [end, startVec]
  );
  const tempVec = useMemo(() => new THREE.Vector3(), []);
  const progressRef = useRef(offset);

  useFrame((_, delta) => {
    if (!ref.current) return;
    progressRef.current = (progressRef.current + delta * speed) % 1;
    tempVec.copy(deltaVec).multiplyScalar(progressRef.current).add(startVec);
    ref.current.position.copy(tempVec);
  });

  return (
    <mesh ref={ref} position={start}>
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshBasicMaterial color={color} />
    </mesh>
  );
};

const FlowBridge: FC<{
  start: [number, number, number];
  end: [number, number, number];
  color: string;
}> = ({ start, end, color }) => (
  <QuadraticBezierLine
    start={start}
    end={end}
    mid={[start[0] * 0.6, 0.5, start[2] * 0.6]}
    color={color}
    lineWidth={2.5}
    dashed
    dashScale={0.6}
    dashSize={0.2}
    gapSize={0.1}
  />
);

const formatFlow = (value?: number) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "--";

const LegendPill = ({
  color,
  label,
  textClass = "text-slate-200",
}: {
  color: string;
  label: string;
  textClass?: string;
}) => (
  <span
    className={`flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/70 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide ${textClass}`}
  >
    <span
      className="h-2.5 w-2.5 rounded-full"
      style={{ backgroundColor: color }}
    />
    {label}
  </span>
);

const directionLabel = (label: string, value?: number) => (
  <div className="flex items-center gap-1 rounded-full border border-white/10 bg-slate-900/70 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-100">
    <span>{label}</span>
    <span className="text-slate-400">{formatFlow(value)} m³/s</span>
  </div>
);

const System3DScene: FC<System3DSceneProps> = ({
  pumps,
  inflow,
  outflow,
  tunnelFillRatio,
  tunnelLevelL1,
  tunnelLevelL2,
  loading,
}) => {
  const pumpVisuals = useMemo<PumpVisual[]>(() => {
    // Expected pump IDs: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4
    const expectedPumpIds = ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '2.3', '2.4'];
    
    return expectedPumpIds.map((pumpId) => {
      // Find matching pump from data (handle both "1.1" and "P1.1" formats)
      const source = pumps?.find(p => 
        p.pump_id === pumpId || 
        p.pump_id === `P${pumpId}` || 
        p.pump_id.replace('P', '') === pumpId
      );
      const health = classifyState(source?.state);
      return {
        id: pumpId,
        state: source?.state,
        frequency: source?.frequency_hz ?? 0,
        power: source?.power_kw ?? 0,
        health,
        color: pumpPalette[health],
        accent: pumpAccentPalette[health],
        size: getPumpSize(source?.pump_id || pumpId),
      };
    });
  }, [pumps]);

  const pumpPositions = useMemo<[number, number, number][]>(() => {
    // Arrange pumps in two vertical columns matching the diagram:
    // Left column (1.x): 1.1 (bottom), 1.2, 1.3, 1.4 (top)
    // Right column (2.x): 2.1 (bottom), 2.2, 2.3, 2.4 (top)
    return pumpVisuals.map((pump, index) => {
      const pumpId = pump.id;
      const isGroup1 = pumpId.startsWith('1.');
      const pumpNum = parseInt(pumpId.split('.')[1]); // 1, 2, 3, or 4
      
      // Left column (1.x) at x = -2.5, Right column (2.x) at x = 2.5
      const x = isGroup1 ? -2.5 : 2.5;
      // Vertical spacing: bottom pump at z = -3, top pump at z = 3
      // pumpNum 1 = bottom, pumpNum 4 = top
      const z = -3 + (pumpNum - 1) * 2; // -3, -1, 1, 3
      
      return [x, 0, z];
    });
  }, [pumpVisuals]);

  const tunnelLevels = useMemo<WastewaterUnitVisual[]>(() => {
    // Use actual tunnel levels if provided, otherwise use inflow/outflow as fallback
    const l1Level = tunnelLevelL1 ?? (inflow ?? 0);
    // L2 is always at 30 meters
    const l2Level = 30.0;
    
    // Normalize levels (assuming 0-8m range for L1, but L2 is at 30m so we'll show it at max)
    const l1Normalized = clamp01(l1Level / 8.0);
    const l2Normalized = 1.0; // L2 is always at 30m, show as full
    
    return [
      {
        id: "L1",
        loadFactor: l1Normalized,
        color: l1Normalized > 0.7 ? "#f472b6" : l1Normalized > 0.4 ? "#a5b4fc" : "#60a5fa",
        position: [-6.5, 0, 0] as [number, number, number], // Left side (inlet)
      },
      {
        id: "L2",
        loadFactor: l2Normalized,
        color: "#60a5fa", // Always at 30m, use consistent blue color
        position: [6.5, 0, 0] as [number, number, number], // Right side (outlet)
      },
    ];
  }, [tunnelLevelL1, inflow]);

  const activeCount = pumpVisuals.filter(
    (pump) => pump.health === "active"
  ).length;
  const faultCount = pumpVisuals.filter(
    (pump) => pump.health === "fault"
  ).length;
  const boosterCount = pumpVisuals.filter(
    (pump) => pump.size === "small"
  ).length;
  const boosterActive = pumpVisuals.filter(
    (pump) => pump.size === "small" && pump.health === "active"
  ).length;
  const primaryTotal = Math.max(pumpVisuals.length - boosterCount, 0);
  const primaryActive = Math.max(activeCount - boosterActive, 0);
  const normalizedFill = clamp01(tunnelFillRatio ?? 0);
  const tunnelFillPercent = Math.round(normalizedFill * 100);

  // Flow indicators for F1 and F2
  const f1Position: [number, number, number] = [-8, 0.5, 0];
  const f2Position: [number, number, number] = [8, 0.5, 0];

  return (
    <div className="relative h-96 w-full overflow-hidden rounded-2xl border border-white/5 bg-gradient-to-br from-slate-950 via-slate-900 to-black">
      <Canvas shadows camera={{ position: [0, 8, 14], fov: 45 }} dpr={[1, 2]}>
        <color attach="background" args={["#01030a"]} />
        <ambientLight intensity={0.45} />
        <directionalLight
          position={[8, 12, 6]}
          intensity={1.2}
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
        />
        <spotLight
          position={[-7, 10, -5]}
          angle={0.5}
          intensity={0.7}
          penumbra={0.35}
        />
        <group position={[0, -0.2, 0]} rotation={[0, 0, 0]}>
          <Grid
            args={[20, 20]}
            position={[0, -0.5, 0]}
            cellSize={0.75}
            cellThickness={0.4}
            sectionSize={3}
            sectionThickness={0.8}
            fadeDistance={14}
            fadeStrength={1.5}
            infiniteGrid
            followCamera={false}
            sectionColor="#0f172a"
            cellColor="#1d2538"
          />
          <ChannelBase length={13} width={1.6} />
          <TunnelWater
            ratio={tunnelFillRatio ?? 0.45}
            length={12.4}
            width={1.3}
          />
          <Sparkles
            count={25}
            size={2.5}
            scale={[12, 0.3, 1.2]}
            position={[0, 0, 0]}
            speed={0.3}
            color="#22d3ee"
          />
          <mesh position={[0, -0.35, 0]}>
            <boxGeometry args={[12.8, 0.05, 0.2]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          <mesh position={[0, -0.35, 0]}>
            <boxGeometry args={[0.2, 0.05, 4.8]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          {/* Inlet pipe from L1 to pump columns */}
          <mesh position={[-4.5, -0.25, 0]}>
            <boxGeometry args={[2, 0.1, 0.12]} />
            <meshStandardMaterial color="#38bdf8" opacity={0.4} transparent />
          </mesh>
          {/* Vertical risers from main pipe to pump columns */}
          <mesh position={[-2.5, -0.25, -3]}>
            <boxGeometry args={[0.12, 0.1, 6]} />
            <meshStandardMaterial color="#38bdf8" opacity={0.4} transparent />
          </mesh>
          <mesh position={[2.5, -0.25, -3]}>
            <boxGeometry args={[0.12, 0.1, 6]} />
            <meshStandardMaterial color="#38bdf8" opacity={0.4} transparent />
          </mesh>
          
          {/* Common discharge header (vertical pipe on right side) */}
          <mesh position={[4.5, -0.25, 0]}>
            <boxGeometry args={[0.12, 0.1, 6]} />
            <meshStandardMaterial color="#f472b6" opacity={0.5} transparent />
          </mesh>
          {/* Horizontal discharge pipe from header to L2 */}
          <mesh position={[5.5, -0.25, 0]}>
            <boxGeometry args={[1, 0.1, 0.12]} />
            <meshStandardMaterial color="#f472b6" opacity={0.5} transparent />
          </mesh>
          
          {pumpVisuals.map((pump, index) => {
            const pos = pumpPositions[index];
            const isGroup1 = pump.id.startsWith('1.');
            
            // Inlet pipe from riser to pump
            const inletPipeStart: [number, number, number] = [
              isGroup1 ? -2.5 : 2.5,
              -0.25,
              pos[2]
            ];
            const inletPipeLength = Math.abs(pos[0] - inletPipeStart[0]);
            
            // Outlet pipe from pump to common header
            const outletPipeStart: [number, number, number] = [
              pos[0],
              -0.25,
              pos[2]
            ];
            const outletPipeEnd: [number, number, number] = [
              4.5,
              -0.25,
              pos[2]
            ];
            const outletPipeLength = Math.abs(outletPipeEnd[0] - outletPipeStart[0]);
            
            const connectorColor =
              pump.size === "small" ? BOOSTER_ACCENT : pump.accent;
            const connectorOpacity = pump.size === "small" ? 0.65 : 0.35;
            
            return (
              <group key={pump.id}>
                {/* Inlet pipe from riser to pump */}
                <mesh position={[
                  (inletPipeStart[0] + pos[0]) / 2,
                  -0.25,
                  pos[2]
                ]}>
                  <boxGeometry args={[inletPipeLength, 0.1, 0.12]} />
                  <meshStandardMaterial
                    color={connectorColor}
                    opacity={connectorOpacity * 0.6}
                    transparent
                  />
                </mesh>
                {/* Outlet pipe from pump to common header */}
                <mesh position={[
                  (outletPipeStart[0] + outletPipeEnd[0]) / 2,
                  -0.25,
                  pos[2]
                ]}>
                  <boxGeometry args={[outletPipeLength, 0.1, 0.12]} />
                  <meshStandardMaterial
                    color={connectorColor}
                    opacity={connectorOpacity * 0.6}
                    transparent
                  />
                </mesh>
                <PumpNode pump={pump} position={pos} index={index} />
              </group>
            );
          })}
          {tunnelLevels.map((unit) => (
            <TunnelLevelIndicator 
              key={unit.id} 
              unit={unit} 
              level={unit.id === "L1" ? (tunnelLevelL1 ?? 0) : 30.0} 
            />
          ))}
          {/* F1 (inlet) flow to L1 */}
          <FlowBridge
            start={[-8, 0.5, 0]}
            end={[-6.5, 0.5, 0]}
            color="#38bdf8"
          />
          <FlowPulse
            start={[-8, 0.5, 0]}
            end={[-6.5, 0.5, 0]}
            color="#38bdf8"
            speed={0.5}
          />
          
          {/* Flow from L1 to pump columns */}
          <FlowPulse
            start={[-6.5, 0.1, 0]}
            end={[-4.5, -0.25, 0]}
            color="#38bdf8"
            speed={0.4}
          />
          
          {/* Flow from pumps through common header to L2 */}
          {pumpVisuals.map((pump, index) => {
            if (pump.health !== "active") return null;
            const pos = pumpPositions[index];
            return (
              <FlowPulse
                key={`pump-flow-${pump.id}`}
                start={[pos[0], 0.1, pos[2]]}
                end={[4.5, -0.25, pos[2]]}
                color={pump.accent}
                speed={0.3 + (index % 3) * 0.1}
                offset={index * 0.15}
              />
            );
          })}
          
          {/* Flow from common header to L2 and F2 */}
          <FlowPulse
            start={[4.5, -0.25, 0]}
            end={[6.5, 0.1, 0]}
            color="#f472b6"
            speed={0.4}
          />
          <FlowBridge
            start={[6.5, 0.1, 0]}
            end={[6.5, 0.5, 0]}
            color="#f472b6"
          />
          {/* F2 (outlet) flow from L2 */}
          <FlowBridge
            start={[6.5, 0.5, 0]}
            end={[8, 0.5, 0]}
            color="#f472b6"
          />
          <FlowPulse
            start={[6.5, 0.5, 0]}
            end={[8, 0.5, 0]}
            color="#f472b6"
            speed={0.5}
          />
        </group>
        <OrbitControls enablePan={false} maxPolarAngle={Math.PI / 2.2} />
      </Canvas>
      <div className="pointer-events-none absolute left-4 top-4 flex flex-col gap-2">
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
          Legend
        </span>
        <div className="flex flex-wrap gap-2">
          <LegendPill color="#22d3ee" label="Active" />
          <LegendPill
            color="#475569"
            label="Standby"
            textClass="text-slate-400"
          />
          <LegendPill color="#fb7185" label="Fault" textClass="text-rose-100" />
        </div>
        <div className="flex flex-wrap gap-2">
          <LegendPill color="#1f8ef1" label="Primary pump" />
          <LegendPill
            color={BOOSTER_ACCENT}
            label="Booster P1.1 / P2.1"
            textClass="text-amber-100"
          />
          <LegendPill
            color="#a5b4fc"
            label="Tunnel L1 / L2"
            textClass="text-blue-100"
          />
        </div>
      </div>
      <div className="pointer-events-none absolute bottom-4 left-4 flex flex-col gap-2 rounded-2xl border border-white/10 bg-slate-950/70 px-4 py-3 text-xs font-semibold text-white min-w-[230px]">
        <div className="flex items-center justify-between text-sm">
          <span>Primary pumps</span>
          <span className="text-sky-200">
            {primaryTotal ? `${primaryActive}/${primaryTotal} active` : "—"}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span>Booster pumps</span>
          <span className="text-amber-200">
            {boosterCount ? `${boosterActive}/${boosterCount}` : "—"}
          </span>
        </div>
        <span className="text-slate-400">Faults detected: {faultCount}</span>
      </div>
      <div className="pointer-events-none absolute bottom-4 right-4 flex flex-col gap-2 text-[11px] font-semibold uppercase tracking-wide text-white">
        {directionLabel("F1 Inflow", inflow)}
        {directionLabel("F2 Outflow", outflow)}
      </div>
      {loading && (
        <div className="pointer-events-auto absolute inset-0 flex items-center justify-center bg-slate-950/70 text-xs uppercase tracking-wide text-slate-300">
          Calibrating 3D layout…
        </div>
      )}
    </div>
  );
};

export default System3DScene;
