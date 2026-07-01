import os
import cv2
import base64

def generate_video_thumbnail(video_path, thumbnail_path):
    """Generate a thumbnail from the first frame of a video using OpenCV"""
    try:
        cap = cv2.VideoCapture(video_path)
        success, frame = cap.read()
        if success:
            # Resize while maintaining aspect ratio (e.g., max width 400)
            height, width = frame.shape[:2]
            max_width = 400
            if width > max_width:
                scaling_factor = max_width / float(width)
                frame = cv2.resize(frame, None, fx=scaling_factor, fy=scaling_factor, interpolation=cv2.INTER_AREA)
            
            cv2.imwrite(thumbnail_path, frame)
            cap.release()
            return True
        cap.release()
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
    return False
