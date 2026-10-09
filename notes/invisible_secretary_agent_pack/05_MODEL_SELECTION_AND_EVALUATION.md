# Local Model Selection and Evaluation

## Candidate
Start by benchmarking Qwen2.5-1.5B-Instruct quantized for the target device, with Qwen2.5-0.5B-Instruct as a smaller baseline. Confirm model licensing, runtime compatibility, and actual device performance before committing.

## Model role
The model performs bounded intent classification and parameter extraction. It is not the policy engine and should not execute tools directly.

## Runtime options
Choose based on target platform and measured support:
- `llama.cpp`/GGUF where supported by the selected model and build.
- `ONNX Runtime` only if a compatible exported model and operators are available.
- Other local inference runtimes only after a working compatibility test.

Do not assume all quantization formats or runtimes are interchangeable.

## Evaluation dataset
Build a labelled dataset of 200–500 realistic requests:
- clear requests for each supported intent
- paraphrases and typos
- ambiguous or incomplete requests
- multiple-intent requests
- out-of-scope requests
- adversarial instructions embedded in user content
- requests for actions that require approval

## Metrics
- Intent accuracy and per-class precision/recall.
- Parameter exact-match or field-level accuracy.
- Invalid JSON/schema rate.
- Abstention/escalation precision and recall.
- Unsafe routing rate; target zero in the evaluation set.
- Median and p95 latency.
- Peak RAM and model footprint.
- Performance under CPU-only conditions if relevant.

## Selection rule
Choose the smallest model that meets the measured quality and latency requirements. If the small model is unreliable on a class, use deterministic rules for that class or require clarification rather than hiding the failure.
