import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'

/** 3D 그래프 캔버스 골격. Phase 5에서 노드·엣지 인스턴스 렌더링으로 교체한다. */
export function GraphScene() {
  return (
    <Canvas camera={{ position: [0, 0, 8] }}>
      <ambientLight intensity={0.5} />
      <pointLight position={[10, 10, 10]} />
      <mesh>
        <sphereGeometry args={[1, 32, 32]} />
        <meshStandardMaterial color="#4f8cff" />
      </mesh>
      <OrbitControls />
    </Canvas>
  )
}
