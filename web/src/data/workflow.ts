import type {
  Correction,
  Version,
  ReviewTask,
  GoldenSample,
  RegressionTest,
  UserUpload,
  CoordinateTransform,
  Metric,
  Phase,
} from "./types";

// 教材版权数据不随源码发布，保留类型与空结构。
export const corrections: Correction[] = [];
export const versions: Version[] = [];
export const reviewTasks: ReviewTask[] = [];
export const goldenSamples: GoldenSample[] = [];
export const regressionTests: RegressionTest[] = [];
export const userUploads: UserUpload[] = [];
export const coordinateTransforms: CoordinateTransform[] = [];
export const metrics: Metric[] = [];
export const phases: Phase[] = [];