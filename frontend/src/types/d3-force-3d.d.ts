// d3-force-3d 는 타입 정의를 제공하지 않는다. 쓰는 부분만 선언한다.
declare module 'd3-force-3d' {
  export interface SimNode {
    index?: number
    x?: number
    y?: number
    z?: number
    vx?: number
    vy?: number
    vz?: number
    [key: string]: unknown
  }
  interface Force {
    (alpha: number): void
  }
  interface Simulation {
    force(name: string, force: unknown): Simulation
    stop(): Simulation
    tick(iterations?: number): Simulation
    nodes(): SimNode[]
  }
  interface LinkForce extends Force {
    id(fn: (n: SimNode) => string): LinkForce
    distance(d: number | ((l: { source: SimNode; target: SimNode; same: boolean }) => number)): LinkForce
    strength(s: number | ((l: { same: boolean }) => number)): LinkForce
  }
  interface StrengthForce extends Force {
    strength(s: number | ((n: SimNode) => number)): StrengthForce
  }
  export function forceSimulation(nodes: SimNode[], numDimensions?: number): Simulation
  export function forceLink(links: object[]): LinkForce
  export function forceManyBody(): StrengthForce & { distanceMax(d: number): StrengthForce }
  export function forceCenter(x?: number, y?: number, z?: number): Force
  export function forceX(x: number | ((n: SimNode) => number)): StrengthForce
  export function forceY(y: number | ((n: SimNode) => number)): StrengthForce
  export function forceZ(z: number | ((n: SimNode) => number)): StrengthForce
}
