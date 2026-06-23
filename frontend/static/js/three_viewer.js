import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const wrap = document.getElementById('threeCanvasWrap');
const statusEl = document.getElementById('viewerStatus');

const STRUCTURES = {
  cerebrum: { label: '대뇌', color: 0x60a5fa },
  cerebellum: { label: '소뇌', color: 0x34d399 },
  brainstem: { label: '뇌간', color: 0xf59e0b },
  hippocampus: { label: '해마', color: 0xa78bfa },
  tumor: { label: '종양', color: 0xf43f5e },
};

let scene;
let camera;
let renderer;
let controls;
let currentObject = null;
let structureGroup = null;
let loadedStructures = {};
let scrollRotationTarget = 0;
let scrollTiltTarget = 0;
let pageScrollProgress = 0;

function setStatus(message) {
  if (statusEl) statusEl.textContent = message;
}

function activeModel() {
  return structureGroup || currentObject;
}

function updatePageScrollProgress() {
  const doc = document.documentElement;
  const maxScroll = Math.max(doc.scrollHeight - window.innerHeight, 1);
  pageScrollProgress = THREE.MathUtils.clamp(window.scrollY / maxScroll, 0, 1);
}

function handleCanvasWheel(event) {
  event.preventDefault();
  scrollRotationTarget += event.deltaY * 0.006;
  scrollTiltTarget = THREE.MathUtils.clamp(scrollTiltTarget + event.deltaX * 0.003, -0.5, 0.5);
  setStatus('스크롤로 3D 모델을 회전하고 있습니다. 마우스 드래그로도 방향을 조정할 수 있습니다.');
}

function resetScrollMotion() {
  scrollRotationTarget = 0;
  scrollTiltTarget = 0;
  updatePageScrollProgress();
}

function applyScrollMotion() {
  const object = activeModel();
  if (!object) return;

  const targetY = scrollRotationTarget + pageScrollProgress * Math.PI * 2.0;
  const targetX = scrollTiltTarget + Math.sin(pageScrollProgress * Math.PI) * 0.18;
  const targetZ = Math.sin(pageScrollProgress * Math.PI * 2.0) * 0.04;

  object.rotation.y += (targetY - object.rotation.y) * 0.08;
  object.rotation.x += (targetX - object.rotation.x) * 0.08;
  object.rotation.z += (targetZ - object.rotation.z) * 0.08;
}

function initScene() {
  wrap.innerHTML = '';
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f172a);

  camera = new THREE.PerspectiveCamera(60, wrap.clientWidth / wrap.clientHeight, 0.1, 1000);
  camera.position.set(2.5, 2.5, 3.2);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.domElement.id = 'viewerCanvas';
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(wrap.clientWidth, wrap.clientHeight || 560);
  wrap.appendChild(renderer.domElement);

  const light1 = new THREE.DirectionalLight(0xffffff, 1.1);
  light1.position.set(3, 4, 5);
  scene.add(light1);

  const light2 = new THREE.DirectionalLight(0xffffff, 0.45);
  light2.position.set(-3, 2, -4);
  scene.add(light2);
  scene.add(new THREE.AmbientLight(0xffffff, 0.58));

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.enableZoom = false;

  renderer.domElement.addEventListener('wheel', handleCanvasWheel, { passive: false });
  window.addEventListener('scroll', updatePageScrollProgress, { passive: true });
  updatePageScrollProgress();
  animate();
}

function animate() {
  requestAnimationFrame(animate);
  applyScrollMotion();
  controls?.update();
  renderer?.render(scene, camera);
}

function removeObject(object) {
  if (!object) return;
  scene.remove(object);
  object.traverse?.((child) => {
    child.geometry?.dispose?.();
    if (Array.isArray(child.material)) {
      child.material.forEach((material) => material.dispose?.());
    } else {
      child.material?.dispose?.();
    }
  });
}

function clearSceneModels() {
  removeObject(currentObject);
  removeObject(structureGroup);
  currentObject = null;
  structureGroup = null;
  loadedStructures = {};
  resetScrollMotion();
}

function fitCameraToObject(object) {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) return;

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const distance = maxDim * 1.8;

  camera.position.set(center.x + distance, center.y + distance * 0.7, center.z + distance);
  camera.near = Math.max(distance / 100, 0.01);
  camera.far = Math.max(distance * 10, 1000);
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

function tintModel(object, color, opacity = 0.72) {
  object.traverse((child) => {
    if (!child.isMesh) return;
    child.material = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.52,
      metalness: 0.04,
      transparent: opacity < 1,
      opacity,
      depthWrite: opacity >= 1,
    });
  });
}

function showSample() {
  clearSceneModels();
  structureGroup = new THREE.Group();

  const samples = [
    ['cerebrum', new THREE.SphereGeometry(1.0, 32, 20), [-0.25, 0.2, 0]],
    ['cerebellum', new THREE.SphereGeometry(0.48, 24, 16), [0.55, -0.58, 0.05]],
    ['brainstem', new THREE.CylinderGeometry(0.18, 0.24, 0.9, 24), [0.2, -1.0, 0]],
    ['hippocampus', new THREE.TorusGeometry(0.28, 0.08, 12, 36, Math.PI * 1.3), [-0.72, -0.22, 0.18]],
    ['tumor', new THREE.IcosahedronGeometry(0.18, 1), [-0.18, 0.42, 0.7]],
  ];

  samples.forEach(([name, geometry, position]) => {
    const material = new THREE.MeshStandardMaterial({
      color: STRUCTURES[name].color,
      roughness: 0.48,
      transparent: name === 'tumor',
      opacity: name === 'tumor' ? 0.9 : 0.72,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(...position);
    mesh.name = name;
    loadedStructures[name] = mesh;
    structureGroup.add(mesh);
  });

  scene.add(structureGroup);
  syncStructureVisibility();
  fitCameraToObject(structureGroup);
  setStatus('샘플 구조를 표시했습니다. 스크롤하면 3D 모델이 회전합니다.');
}

function loadGLBModel(url) {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(url, (gltf) => resolve(gltf.scene), undefined, reject);
  });
}

function getPatientStudy() {
  const patientCode = document.getElementById('patientCode').value.trim() || 'P001';
  const studyLabel = document.getElementById('studyLabel').value.trim() || 'T08';
  return { patientCode, studyLabel };
}

function getStructureUrl(name) {
  const { patientCode, studyLabel } = getPatientStudy();
  if (name === 'tumor') return `/media/models/${patientCode}/${studyLabel}/lesion_model.glb`;
  return `/media/models/${patientCode}/${studyLabel}/structures/${name}.glb`;
}

function checkedStructureNames() {
  return Array.from(document.querySelectorAll('[data-structure]'))
    .filter((input) => input.checked)
    .map((input) => input.dataset.structure);
}

function syncStructureVisibility() {
  document.querySelectorAll('[data-structure]').forEach((input) => {
    const object = loadedStructures[input.dataset.structure];
    if (object) object.visible = input.checked;
  });
}

async function loadStructures() {
  clearSceneModels();
  structureGroup = new THREE.Group();
  scene.add(structureGroup);

  const names = checkedStructureNames();
  if (!names.length) {
    setStatus('표시할 구조를 하나 이상 선택하세요.');
    return;
  }

  setStatus('구조별 GLB를 불러오는 중입니다...');
  const failed = [];

  for (const name of names) {
    try {
      const object = await loadGLBModel(getStructureUrl(name));
      object.name = name;
      tintModel(object, STRUCTURES[name].color, name === 'tumor' ? 0.92 : 0.68);
      loadedStructures[name] = object;
      structureGroup.add(object);
    } catch {
      failed.push(STRUCTURES[name].label);
    }
  }

  syncStructureVisibility();

  if (!Object.keys(loadedStructures).length) {
    showSample();
    setStatus(`GLB 파일을 찾지 못해 샘플 구조로 대체했습니다. 누락: ${failed.join(', ')}`);
    return;
  }

  fitCameraToObject(structureGroup);
  const loadedLabels = Object.keys(loadedStructures).map((name) => STRUCTURES[name].label).join(', ');
  const failedText = failed.length ? ` / 누락: ${failed.join(', ')}` : '';
  setStatus(`로딩 완료: ${loadedLabels}${failedText}. 스크롤로 모델을 회전할 수 있습니다.`);
}

async function loadSingleModel(url) {
  clearSceneModels();
  setStatus('단일 GLB 모델을 불러오는 중입니다...');
  try {
    currentObject = await loadGLBModel(url);
    tintModel(currentObject, STRUCTURES.tumor.color, 0.86);
    scene.add(currentObject);
    fitCameraToObject(currentObject);
    setStatus('단일 GLB 모델을 표시했습니다. 스크롤로 모델을 회전할 수 있습니다.');
  } catch {
    showSample();
    setStatus('GLB 파일을 찾지 못해 샘플 구조로 대체했습니다.');
  }
}

document.getElementById('sampleBtn').addEventListener('click', showSample);
document.getElementById('loadStructuresBtn').addEventListener('click', loadStructures);
document.getElementById('loadModelBtn').addEventListener('click', () => {
  loadSingleModel(document.getElementById('modelUrl').value.trim());
});
document.querySelectorAll('[data-structure]').forEach((input) => {
  input.addEventListener('change', syncStructureVisibility);
});
window.addEventListener('resize', () => {
  if (!renderer || !camera) return;
  camera.aspect = wrap.clientWidth / wrap.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(wrap.clientWidth, wrap.clientHeight || 560);
});

initScene();
showSample();
