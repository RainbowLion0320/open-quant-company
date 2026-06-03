import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface HindsightSceneObjects {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  sphereGeo: THREE.SphereGeometry;
  starfield: THREE.Points;
}

export function createHindsightScene(container: HTMLElement): HindsightSceneObjects {
  const width = container.clientWidth;
  const height = container.clientHeight;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#02060d");

  const camera = new THREE.PerspectiveCamera(55, width / height, 0.5, 2000);
  camera.position.set(0, 0, 160);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.15;
  controls.minDistance = 30;
  controls.maxDistance = 600;
  controls.target.set(0, 0, 0);

  scene.add(new THREE.AmbientLight(0x334466, 1.2));
  const pointLight = new THREE.PointLight(0x00d4ff, 0.6, 500);
  pointLight.position.set(0, 0, 200);
  scene.add(pointLight);

  const sphereGeo = new THREE.SphereGeometry(1, 24, 16);
  const starfield = createStarfield();
  scene.add(starfield);

  return { scene, camera, renderer, controls, sphereGeo, starfield };
}

export function resizeHindsightScene(objects: HindsightSceneObjects, container: HTMLElement) {
  const width = container.clientWidth;
  const height = container.clientHeight;
  objects.renderer.setSize(width, height);
  objects.camera.aspect = width / height;
  objects.camera.updateProjectionMatrix();
}

export function disposeHindsightScene(objects: HindsightSceneObjects | null) {
  if (!objects) return;
  objects.controls.dispose();
  objects.sphereGeo.dispose();
  objects.starfield.geometry.dispose();
  const material = objects.starfield.material;
  if (Array.isArray(material)) material.forEach(item => item.dispose());
  else material.dispose();
  objects.renderer.dispose();
}

function createStarfield(): THREE.Points {
  const starCount = 600;
  const starsGeo = new THREE.BufferGeometry();
  const starPositions = new Float32Array(starCount * 3);
  for (let i = 0; i < starCount; i++) {
    starPositions[i * 3] = (Math.random() - 0.5) * 800;
    starPositions[i * 3 + 1] = (Math.random() - 0.5) * 800;
    starPositions[i * 3 + 2] = (Math.random() - 0.5) * 800;
  }
  starsGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
  const starsMat = new THREE.PointsMaterial({
    color: 0x334466,
    size: 0.6,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  return new THREE.Points(starsGeo, starsMat);
}
