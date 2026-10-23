import cv2
import numpy as np
import os
import glob

class SourceVerifier:
    def __init__(self, dataset_path="Correct Sources Dataset"):
        self.dataset_path = dataset_path
        
        # Coordinates based on the circled regions (resized to 1024x576)
        self.rois = {
            'Top_Left_Inductor_Source': (460, 550, 40, 160),
            'Top_Right_Inductor_Source': (570, 670, 40, 160),
            'Bottom_Left_Source': (370, 460, 470, 560),
            'Bottom_Middle_Source': (530, 610, 470, 560),
            'Bottom_Right_Source': (620, 690, 470, 560)
        }
        self.reference_ranges = {}

    def _get_color_density(self, img):
        img_resized = cv2.resize(img, (1024, 576))
        hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)
        
        # Color masks
        mask_r = cv2.inRange(hsv, (0, 100, 50), (12, 255, 255)) + cv2.inRange(hsv, (160, 100, 50), (180, 255, 255))
        mask_b = cv2.inRange(hsv, (0, 0, 0), (180, 255, 60))
        mask_g = cv2.inRange(hsv, (40, 50, 50), (85, 255, 255))
        
        density = {}
        for name, (x1, x2, y1, y2) in self.rois.items():
            r = np.sum(mask_r[y1:y2, x1:x2] > 0)
            b = np.sum(mask_b[y1:y2, x1:x2] > 0)
            g = np.sum(mask_g[y1:y2, x1:x2] > 0)
            density[name] = {'R': int(r), 'B': int(b), 'G': int(g)}
        return density

    def train(self, max_images=20):
        print(f"Training on dataset: {self.dataset_path}")
        files = glob.glob(os.path.join(self.dataset_path, '*.jpg'))[:max_images]
        if not files:
            print("No files found!")
            return False
            
        stats = {name: {'R': [], 'B': [], 'G': []} for name in self.rois}
        
        for f in files:
            img = cv2.imread(f)
            if img is not None:
                d = self._get_color_density(img)
                for name in self.rois:
                    stats[name]['R'].append(d[name]['R'])
                    stats[name]['B'].append(d[name]['B'])
                    stats[name]['G'].append(d[name]['G'])
                    
        self.reference_ranges = {}
        for name in self.rois:
            self.reference_ranges[name] = {}
            for c in ['R', 'B', 'G']:
                vals = stats[name][c]
                # Allow a margin of error (20%)
                mean_val = np.mean(vals)
                std_val = np.std(vals)
                # Ensure a minimum range width for stability
                self.reference_ranges[name][c] = {
                    'min': max(0, int(mean_val - 2.5 * std_val - 50)),
                    'max': int(mean_val + 2.5 * std_val + 500) # generous max
                }
        print("Training complete.")
        return True

    def verify(self, img_path):
        if not self.reference_ranges:
            if not self.train():
                return
                
        img = cv2.imread(img_path)
        if img is None:
            print(f"Failed to load {img_path}")
            return
            
        print(f"\nVerifying {os.path.basename(img_path)}:")
        density = self._get_color_density(img)
        
        all_pass = True
        failed_sources = []
        
        for name in self.rois:
            source_pass = True
            reasons = []
            
            for c in ['R', 'B', 'G']:
                val = density[name][c]
                expected_min = self.reference_ranges[name][c]['min']
                expected_max = self.reference_ranges[name][c]['max']
                
                # We only heavily penalize if an expected color is missing
                # Or if an unexpected color appears
                
                # Missing expected color
                if expected_min > 50 and val < expected_min * 0.5:
                    source_pass = False
                    reasons.append(f"Missing {c}")
                
                # Unexpected color appeared
                if expected_max < 150 and val > 300:
                    source_pass = False
                    reasons.append(f"Unexpected {c}")
            
            # Cross-check for red wire position for top inductors
            if name == 'Top_Left_Inductor_Source' and density['Top_Left_Inductor_Source']['R'] > density['Top_Right_Inductor_Source']['R'] + 200:
                source_pass = False
                reasons.append("Red wire on wrong inductor")
                
            if source_pass:
                print(f"  [PASS] {name}")
            else:
                print(f"  [FAIL] {name} - {', '.join(reasons)}")
                failed_sources.append(name)
                all_pass = False
                
        if all_pass:
            print("  OVERALL RESULT: PASS")
        else:
            print(f"  OVERALL RESULT: FAIL (Failed sources: {', '.join(failed_sources)})")

if __name__ == '__main__':
    verifier = SourceVerifier()
    verifier.verify(r'C:\Users\SM 461\.gemini\antigravity\brain\aee83f41-828f-4235-9706-324cb50bcb81\.user_uploaded\media_1787737616374.png')
    verifier.verify(r'C:\Users\SM 461\Desktop\Try 2\Wiring Dataset\Wrong Wiring\case 1\wrongwiring_case 1 (1).jpg')
    verifier.verify(r'C:\Users\SM 461\Desktop\Try 2\Wiring Dataset\Wrong Wiring\case 2\wrongwiring_case 2 (1).jpg')
