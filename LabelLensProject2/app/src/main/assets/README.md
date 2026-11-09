best.tflite is the supplied Ultralytics 8.4.171 product_name detector.
FP32 input: [1,3,320,320], NCHW RGB / 255.
FP32 output: [1,5,2100], normalized center-x/center-y/width/height + class score.
No embedded NMS. The adapter applies letterboxing and external NMS.
Re-inspect input/output semantics before swapping in a different model.
