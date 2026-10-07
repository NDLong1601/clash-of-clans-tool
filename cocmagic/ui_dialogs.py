"""Recognition of the game's centered, two-button confirmation dialog."""

from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

from cocmagic import config
OKAY_TEMPLATE = config.asset("okay.png")
CONFIRM_TEMPLATES = (
    config.asset("confirmwall.png"),
    config.asset("confirmupwall.png"),
    config.asset("oknangcap.png"),
)
BUTTON_REGION = (760, 420, 420, 240)
CONNECTION_TITLE = config.asset("connection_lost_title.png")
TRY_AGAIN_TEMPLATE = config.asset("try_again.png")
LEGACY_CONNECTION = config.asset("Connection_lostt.png")


def find_connection_retry(adb, image: np.ndarray) -> Optional[Tuple[int, int]]:
    """Require Connection lost and Try Again text from the same native modal."""
    if image is None or image.shape[:2] != (config.ANDROID_H, config.ANDROID_W):
        return None
    title = adb.find_template(CONNECTION_TITLE, .80, image,
                              region=(330, 280, 700, 200))
    if isinstance(title, tuple) and len(title) == 2:
        left = max(0, title[0] - 150)
        retry = adb.find_template(TRY_AGAIN_TEMPLATE, .78, image,
                                  region=(left, title[1] + 80, 420, 110))
        if isinstance(retry, tuple) and len(retry) == 2:
            return retry

    # Older Android dialogs have a different panel theme. This template
    # includes the whole message and its Try Again button, whose offset is fixed.
    legacy = adb.find_template(LEGACY_CONNECTION, .82, image,
                               region=(250, 280, 1100, 340))
    if isinstance(legacy, tuple) and len(legacy) == 2:
        template = adb._load_template(LEGACY_CONNECTION)
        if template is not None:
            height, width = template.shape[:2]
            return (legacy[0] - width // 2 + 84,
                    legacy[1] - height // 2 + 175)
    return None


def find_confirmation_button(
    adb,
    image: np.ndarray,
    templates: Sequence[Tuple[str, float]] = ((OKAY_TEMPLATE, .67),),
    region: Tuple[int, int, int, int] = BUTTON_REGION,
) -> Optional[Tuple[int, int]]:
    """Locate the green Okay/Confirm beside orange Cancel on a white dialog.

    The text template alone can also occur elsewhere. Requiring the actual
    two-button modal keeps this from accepting a gem offer or an ordinary UI
    button. Coordinates are for the configured 1600x900 game screen.
    """
    if image is None or image.shape[:2] != (config.ANDROID_H, config.ANDROID_W):
        return None

    for path, threshold in templates:
        point = adb.find_template(path, threshold, image, region=region)
        if not isinstance(point, tuple) or len(point) != 2:
            continue
        x, y = point
        if not (400 <= x < config.ANDROID_W - 50 and 200 <= y < config.ANDROID_H - 50):
            continue

        cancel = image[y - 45:y + 50, x - 400:x - 160]
        panel = image[y - 190:y - 90, x - 350:x + 50]
        if cancel.shape[:2] != (95, 240) or panel.shape[:2] != (100, 400):
            continue
        cancel_hsv = cv2.cvtColor(cancel, cv2.COLOR_BGR2HSV)
        panel_hsv = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)
        orange = cv2.inRange(cancel_hsv, (0, 80, 80), (25, 255, 255))
        white = cv2.inRange(panel_hsv, (0, 0, 170), (180, 85, 255))
        if np.mean(orange > 0) > .45 and np.mean(white > 0) > .60:
            return int(x), int(y)
    return None
