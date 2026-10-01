# `CVFlags` + `CVDetectorProtocol` — Low-Level Design

## Responsibility
Define the GO3 result shape and the interface that consumers depend on.

## `CVFlags` (TypedDict)
| Field | Type | Meaning |
|---|---|---|
| `finger_pointing` | `bool` | Index tip in text region in ≥ 20% of sampled frames |
| `loss_of_place` | `bool` | True if either: averaged iris xy (Euclidean) shifts > 0.10 between consecutive sampled frames ≥ 2 times; or the face disappears for ≥ 3 sampled frames after being detected at least once (a face absent from the very first frame doesn't count — that's a camera/setup problem, not losing place) |

## `CVDetectorProtocol` (Protocol)
| Method | Signature | Implemented by |
|---|---|---|
| `detect` | `(video_path: str) -> CVFlags` | `CVDetector` |

## Diagrams
| Diagram | Link |
|---|---|
| Class diagram | [go3-classes.md](../../uml/class/go3-classes.md) |

## Related
- HLD: [go3-pipeline.md](../../hld/go3-pipeline.md)
- Source: `app/models/cv_detector.py`
