import cv2
import numpy as np
import matplotlib.pyplot as plt

class Matcher:
    class Params:
        def __init__(self):

            self.bidirectional_enable = True
            self.bidirectional_thresh = 2.0
            self.min_points_for_find_homography = 10
            self.detection_params = dict(
                maxCorners=500, qualityLevel=0.01, minDistance=21, blockSize=7
            )
            self.tracking_params = dict(
                winSize=(15, 15),
                maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
                minEigThreshold=5e-4,
            )

    def __init__(self, use_orb=True, params=Params()):
        self.orb = cv2.ORB_create()
        self.use_orb = use_orb
        self._params = params
        self._prev_image = None
        self.features = None
        self._frame_num = 0

    def init(self, image, roi):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self._prev_image = gray
        self.roi = roi
        self.features = cv2.goodFeaturesToTrack(gray, **self._params.detection_params)

    def _calc_orb(self, image):
        kp1, des1 = self.orb.detectAndCompute(self._prev_image,None)
        kp2, des2 = self.orb.detectAndCompute(image,None)
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1,des2)
        matches = sorted(matches, key = lambda x:x.distance)
        # Draw first 10 matches.
        #img3 = cv2.drawMatches(self._prev_image,kp1,image,kp2,matches[:10],None,flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        #plt.imshow(img3),plt.show()

        matches = matches[:20]
        list_kp1 = [kp1[mat.queryIdx].pt for mat in matches]
        list_kp2 = [kp2[mat.trainIdx].pt for mat in matches]
        print(len(list_kp2))
        M, mask = cv2.findHomography(
            np.squeeze(list_kp1), np.squeeze(list_kp2), cv2.RANSAC, 5.0
        )
        return M, mask
    
    def _calc_optical_flow(self, p0, image):
        p1, st1, err1 = cv2.calcOpticalFlowPyrLK(
            self._prev_image, image, p0, None, **self._params.tracking_params
        )
        if self._params.bidirectional_enable:
            p2, st2, err2 = cv2.calcOpticalFlowPyrLK(
                image, self._prev_image, p1, None, **self._params.tracking_params
            )
            proj_err = np.linalg.norm(p2 - p0, axis=1)
            st = np.squeeze(st1 * st2) * (
                proj_err < self._params.bidirectional_thresh
            ).astype("uint8")
        else:
            st = np.squeeze(st1)
        return st, p1 

    
    def __call__(self, image):
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        p0 = np.squeeze(self.features)

        if len(p0) == 0:
            return [], [], []
        
        st, p1 = self._calc_optical_flow(p0, image)
        self.features = cv2.goodFeaturesToTrack(image, **self._params.detection_params)
        self._prev_image = image
        if len(np.squeeze(p0[st > 0])) < self._params.min_points_for_find_homography:
            if self.use_orb is True:
                M, mask = self._calc_orb(image)
                if M is None:
                    return None
            else:
                return None
        else:
            M, mask = cv2.findHomography(
                np.squeeze(p0[st > 0]), np.squeeze(p1[st > 0]), cv2.RANSAC, 5.0
            )
        if M is None and self.use_orb is True:
            M, mask = self._calc_orb(image)
        if M is None:
            return None
        points = []
        point1 = [self.roi[0], self.roi[1]]
        point2 = [self.roi[0] + self.roi[2], self.roi[1]]
        point3 = [self.roi[0] + self.roi[2], self.roi[1] + self.roi[3]]
        point4 = [self.roi[0], self.roi[1] + self.roi[3]]
        coord_of_roi = np.array([point1, point2, point3, point4]).reshape(-1, 1, 2)
        transform_points = cv2.perspectiveTransform(
            coord_of_roi.astype(np.float), M
        ).reshape(-1, 2)
        min_x = np.min(transform_points, axis=0)[0]
        min_y = np.min(transform_points, axis=0)[1]
        max_x = np.max(transform_points, axis=0)[0]
        max_y = np.max(transform_points, axis=0)[1]
        w = max_x - min_x
        h = max_y - min_y
        self.roi = [min_x, min_y, w, h]
        return min_x, min_y, max_x, max_y