import os
import uuid
import cv2
import base64
import binascii
import numpy as np
from uuid import uuid4
from werkzeug.utils import secure_filename

# -----------------------------
# Haar Cascade
# -----------------------------

_face_cascade = None


def get_face_cascade():
    global _face_cascade

    if _face_cascade is None:
        cascade_path = (
            cv2.data.haarcascades +
            "haarcascade_frontalface_default.xml"
        )

        _face_cascade = cv2.CascadeClassifier(cascade_path)

        if _face_cascade.empty():
            raise RuntimeError(
                "Unable to load Haar Cascade model."
            )

    return _face_cascade


# -----------------------------
# Registration Photo Validation
# -----------------------------

def save_photo(photo, captured_photo, upload_folder):
    """
    Save candidate registration photo after validating it with Haar Cascade.

    Exactly one face must be detected.
    """

    # Prefer webcam captured image
    if captured_photo:
        photo_data = captured_photo
    elif photo:
        photo_data = photo
    else:
        return None, "Please capture or upload a photo."

    try:

        # ---------------------------------------------------------
        # 1. Handle webcam Base64 image
        # ---------------------------------------------------------
        if isinstance(photo_data, str) and photo_data.startswith("data:image"):

            encoded_data = photo_data.split(",", 1)[1]

            image_bytes = base64.b64decode(
                encoded_data,
                validate=True
            )

            image_array = np.frombuffer(
                image_bytes,
                dtype=np.uint8
            )

            image = cv2.imdecode(
                image_array,
                cv2.IMREAD_COLOR
            )

        # ---------------------------------------------------------
        # 2. Handle uploaded Flask image
        # ---------------------------------------------------------
        elif hasattr(photo_data, "read"):

            image_bytes = photo_data.read()

            image_array = np.frombuffer(
                image_bytes,
                dtype=np.uint8
            )

            image = cv2.imdecode(
                image_array,
                cv2.IMREAD_COLOR
            )

        else:
            return None, "Invalid photo format."

        # ---------------------------------------------------------
        # 3. Check image
        # ---------------------------------------------------------
        if image is None:
            return None, "Unable to read the photo. Please capture it again."

        # ---------------------------------------------------------
        # 4. Haar Cascade face detection
        # ---------------------------------------------------------
        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

        faces = get_face_cascade().detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60)
        )

        # ---------------------------------------------------------
        # 5. Validate face count
        # ---------------------------------------------------------
        if len(faces) == 0:
            return None, (
                "No face detected. "
                "Please position your face clearly and retake the photo."
            )

        if len(faces) > 1:
            return None, (
                "Multiple faces detected. "
                "Please make sure only you are visible."
            )

        # ---------------------------------------------------------
        # 6. Create upload folder
        # ---------------------------------------------------------
        os.makedirs(
            upload_folder,
            exist_ok=True
        )

        # ---------------------------------------------------------
        # 7. Save image
        # ---------------------------------------------------------
        filename = f"candidate_{uuid.uuid4().hex}.jpg"

        filepath = os.path.join(
            upload_folder,
            filename
        )

        if not cv2.imwrite(filepath, image):
            return None, "Unable to save the photo. Please try again."

        # ---------------------------------------------------------
        # 8. SUCCESS
        # ---------------------------------------------------------
        return filename, None

    except Exception as error:

        print(
            "Photo processing error:",
            repr(error)
        )

        return None, "Unable to process the photo. Please try again."


# -----------------------------
# Live Monitoring
# -----------------------------

def analyze_frame(frame_data):

    try:

        _, encoded_frame = frame_data.split(",", 1)

        image_bytes = base64.b64decode(
            encoded_frame,
            validate=True
        )

        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        image = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if image is None:
            raise ValueError(
                "Unable to decode webcam frame."
            )

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

        faces = get_face_cascade().detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60)
        )

        face_count = len(faces)

        face_boxes = []

        for (x, y, w, h) in faces:

            face_boxes.append({
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h)
            })

        if face_count == 0:

            event_type = "no_face"

            status_label = "No Face Detected"

            details = "No face was found."

        elif face_count == 1:

            event_type = "face_detected"

            status_label = "Face Detected"

            details = "One face detected."

        else:

            event_type = "multiple_faces"

            status_label = "Multiple Faces Detected"

            details = (
                f"{face_count} faces detected."
            )

        return {

            "event_type": event_type,

            "status_label": status_label,

            "details": details,

            "face_count": face_count,

            "face_boxes": face_boxes

        }

    except (ValueError, binascii.Error) as error:

        raise ValueError(str(error))