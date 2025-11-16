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

  useFrame(() => {
    if (!columnRef.current || !beaconRef.current) return;
    const wobble =
      pump.health === "active"
        ? 1 + Math.sin((getNow() + index * 80) * 0.003) * 0.08
        : 1;
    columnRef.current.scale.y = THREE.MathUtils.lerp(
      columnRef.current.scale.y,
      wobble,
      0.08
    );
    const opacityTarget = pump.health === "active" ? 0.85 : 0.25;
    const beaconMaterial = beaconRef.current.material;
    beaconMaterial.opacity = THREE.MathUtils.lerp(
      beaconMaterial.opacity,
      opacityTarget,
      0.1
    );
  });

  const radius = pump.size === "small" ? 0.26 : 0.35;
  const towerHeight = pump.size === "small" ? 0.9 : 1.25;
  const beaconSize = pump.size === "small" ? 0.14 : 0.18;

  return (
    <group position={position}>
      <mesh position={[0, -0.4, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[radius + 0.1, radius + 0.45, 48]} />
        <meshStandardMaterial
          color={pump.accent}
          emissive={pump.accent}
          emissiveIntensity={0.25}
          opacity={0.65}
          transparent
        />
      </mesh>
      <mesh position={[0, -0.15, 0]}>
        <cylinderGeometry args={[radius + 0.08, radius + 0.08, 0.2, 24]} />
        <meshStandardMaterial color="#0f172a" roughness={0.6} metalness={0.1} />
      </mesh>
      <mesh ref={columnRef} position={[0, towerHeight / 2, 0]} castShadow>
        <cylinderGeometry args={[radius, radius, towerHeight, 32]} />
        {pump.size === "small" && (
          <mesh position={[0, towerHeight * 0.4, 0]} castShadow>
            <torusGeometry args={[radius + 0.05, 0.04, 12, 48]} />
            <meshStandardMaterial
              color={BOOSTER_ACCENT}
              emissive={BOOSTER_ACCENT}
              emissiveIntensity={0.6}
              metalness={0.3}
            />
          </mesh>
        )}
        <meshStandardMaterial
          color={pump.color}
          emissive={pump.health === "active" ? pump.color : "#0f172a"}
          emissiveIntensity={pump.health === "active" ? 0.5 : 0.15}
          roughness={0.25}
          metalness={0.3}
        />
      </mesh>
      <mesh ref={beaconRef} position={[0, towerHeight + 0.35, 0]}>
        <sphereGeometry args={[beaconSize, 16, 16]} />
        <meshBasicMaterial color={pump.accent} opacity={0.5} transparent />
      </mesh>
      <Html center distanceFactor={18} position={[0, 1.8, 0]}>
        <div className="rounded-full border border-white/10 bg-slate-900/70 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-100">
          {pump.id}
        </div>
      </Html>
    </group>
  );
};

const WastewaterUnit: FC<{ unit: WastewaterUnitVisual }> = ({ unit }) => (
  <Float
    floatIntensity={0.4 + unit.loadFactor * 0.5}
    speed={0.8 + unit.loadFactor}
  >
    <group position={unit.position}>
      <mesh castShadow>
        <icosahedronGeometry args={[0.9 + unit.loadFactor * 0.3, 1]} />
        <meshStandardMaterial
          color={unit.color}
          emissive={unit.color}
          emissiveIntensity={0.35 + unit.loadFactor * 0.9}
          metalness={0.2}
          roughness={0.15}
        />
      </mesh>
      <Html center distanceFactor={20} position={[0, 1.6, 0]}>
        <div className="rounded-full border border-white/10 bg-slate-900/70 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-blue-50">
          {unit.id}
        </div>
      </Html>
    </group>
  </Float>
);

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
  loading,
}) => {
  const pumpVisuals = useMemo<PumpVisual[]>(() => {
    const slots = 8;
    return new Array(slots).fill(null).map((_, index) => {
      const source = pumps?.[index];
      const health = classifyState(source?.state);
      return {
        id: source?.pump_id ?? `P${index + 1}`,
        state: source?.state,
        frequency: source?.frequency_hz ?? 0,
        power: source?.power_kw ?? 0,
        health,
        color: pumpPalette[health],
        accent: pumpAccentPalette[health],
        size: getPumpSize(source?.pump_id),
      };
    });
  }, [pumps]);

  const pumpPositions = useMemo<[number, number, number][]>(() => {
    return pumpVisuals.map((_, index) => {
      const column = index % 4;
      const row = Math.floor(index / 4);
      const x = -4.5 + column * 3;
      const z = row === 0 ? -2.4 : 2.4;
      return [x, 0, z];
    });
  }, [pumpVisuals]);

  const wastewaterUnits = useMemo<WastewaterUnitVisual[]>(() => {
    const inflowLoad = clamp01((inflow ?? 0) / 8);
    const outflowLoad = clamp01((outflow ?? 0) / 8);
    return [
      {
        id: "L1",
        loadFactor: inflowLoad,
        color: inflowLoad > 0.6 ? "#f472b6" : "#a5b4fc",
        position: [-7.5, 0.8, 0],
      },
      {
        id: "L2",
        loadFactor: outflowLoad,
        color: outflowLoad > 0.6 ? "#f472b6" : "#a5b4fc",
        position: [7.5, 0.8, 0],
      },
    ];
  }, [inflow, outflow]);

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

  const flowStart: [number, number, number] = [-5.8, 0.15, 0];
  const flowEnd: [number, number, number] = [5.8, 0.15, 0];

  return (
    <div className="relative h-96 w-full overflow-hidden rounded-2xl border border-white/5 bg-gradient-to-br from-slate-950 via-slate-900 to-black">
      <Canvas shadows camera={{ position: [0, 7, 12], fov: 42 }} dpr={[1, 2]}>
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
            count={18}
            size={2}
            scale={[10, 0.2, 1]}
            position={[0, 0, 0]}
            speed={0.2}
          />
          <mesh position={[0, -0.35, 0]}>
            <boxGeometry args={[12.8, 0.05, 0.2]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          <mesh position={[0, -0.35, 0]}>
            <boxGeometry args={[0.2, 0.05, 4.8]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          {pumpVisuals.map((pump, index) => {
            const pos = pumpPositions[index];
            const connectorLength = Math.abs(pos[2]) - 1;
            const connectorPosition: [number, number, number] = [
              pos[0],
              -0.25,
              pos[2] > 0
                ? pos[2] - connectorLength / 2
                : pos[2] + connectorLength / 2,
            ];
            const connectorColor =
              pump.size === "small" ? BOOSTER_ACCENT : pump.accent;
            const connectorOpacity = pump.size === "small" ? 0.65 : 0.35;
            return (
              <group key={pump.id}>
                <mesh position={connectorPosition}>
                  <boxGeometry args={[0.12, 0.1, connectorLength]} />
                  <meshStandardMaterial
                    color={connectorColor}
                    opacity={connectorOpacity}
                    transparent
                  />
                </mesh>
                <PumpNode pump={pump} position={pos} index={index} />
              </group>
            );
          })}
          {wastewaterUnits.map((unit) => (
            <WastewaterUnit key={unit.id} unit={unit} />
          ))}
          <FlowBridge
            start={[-6.5, 0, 0]}
            end={[-7.3, 0.8, 0]}
            color="#38bdf8"
          />
          <FlowBridge start={[6.5, 0, 0]} end={[7.3, 0.8, 0]} color="#f472b6" />
          <FlowPulse
            start={flowStart}
            end={flowEnd}
            color="#86efac"
            speed={0.35}
          />
          <FlowPulse
            start={flowStart}
            end={flowEnd}
            color="#14b8a6"
            speed={0.55}
            offset={0.4}
          />
          <FlowPulse
            start={[6.5, 0.1, 0]}
            end={wastewaterUnits[1].position}
            color="#f472b6"
            speed={0.4}
          />
          <FlowPulse
            start={[-6.5, 0.1, 0]}
            end={wastewaterUnits[0].position}
            color="#38bdf8"
            speed={0.4}
            offset={0.5}
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
            label="Wastewater unit"
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
        {directionLabel("Inflow", inflow)}
        {directionLabel("Outflow", outflow)}
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
