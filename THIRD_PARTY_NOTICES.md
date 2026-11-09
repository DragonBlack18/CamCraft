# Third-party notices

Application-specific source and reused Vision Foundation source: MIT, see `LICENSE`.

## YOLOX / OpenCV Zoo

The optional pretrained `object_detection_yolox_2022nov.onnx` is downloaded at first preparation from the OpenCV Zoo. Its source directory declares Apache License 2.0. The model is NOT included in this ZIP. The adapter's preprocessing/postprocessing was implemented with reference to that project's documented interface; notices are retained here out of caution.

- Copyright (c) 2021-2022 Megvii Inc. All rights reserved.
- OpenCV Zoo and its YOLOX contributors, including Sri Siddarth Chakaravarthy (GSoC 2022).
- Source: https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_yolox
- Upstream license: https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/object_detection_yolox/LICENSE
- Apache 2.0 license text: `licenses/Apache-2.0.txt`.

The application is not endorsed by OpenCV or Megvii. Benchmark values from the model author are not certification of this application.

## Tracking

`vision_app/tracker.py` is an independent implementation inspired by the high/low-confidence association principle in Zhang et al., *ByteTrack: Multi-Object Tracking by Associating Every Detection Box*, arXiv:2110.06864. It is not a vendored copy of the official ByteTrack implementation and does not claim its benchmark performance.

## Installed dependencies

Dependency binaries are obtained through pip, not bundled in this source ZIP. Retain their installed license files when redistributing a compiled application. Components include OpenCV (Apache-2.0), the OpenCV Python wheel packaging and its bundled third-party notices, NumPy, SciPy, Pillow, Pydantic and psutil. OpenCV wheels include FFmpeg and additional libraries with their own terms. Tk/Tcl is provided by the Python installation.

See each distribution's metadata/license directory. The application's MIT license does not override dependency/model licenses. No Ultralytics package, weights, Torch runtime or upstream ByteTrack source is redistributed here.


## CamCraft Windows distribution

The frozen Windows builds include Python (PSF license), Tcl/Tk, the runtime libraries listed in `requirements.txt`, the OpenCV Zoo YOLOX ONNX model (Apache-2.0), and a PyInstaller bootloader (GPL with the special distribution exception). The installer is generated with Inno Setup. Original notices are collected in the bundled `licenses/` directory and the exact build environment is recorded in `runtime-manifest.json`. No third-party trademarks imply endorsement.
