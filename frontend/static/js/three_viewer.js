const wrap = document.getElementById('threeCanvasWrap');
let scene, camera, renderer, controls, currentObject;

function initScene() {
  wrap.innerHTML = '';
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f172a);
  camera = new THREE.PerspectiveCamera(60, wrap.clientWidth / wrap.clientHeight, 0.1, 1000);
  camera.position.set(2.5, 2.5, 3.2);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(wrap.clientWidth, wrap.clientHeight || 420);
  wrap.appendChild(renderer.domElement);

  const light1 = new THREE.DirectionalLight(0xffffff, 1.1);
  light1.position.set(3, 4, 5);
  scene.add(light1);
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  animate();
}

function animate() {
  requestAnimationFrame(animate);
  controls?.update();
  renderer?.render(scene, camera);
}

function clearObject() {
  if (currentObject) scene.remove(currentObject);
}

function showSample() {
  clearObject();
  const geometry = new THREE.IcosahedronGeometry(1, 2);
  const material = new THREE.MeshStandardMaterial({ color: 0x4f8cff, roughness: 0.45, metalness: 0.05 });
  currentObject = new THREE.Mesh(geometry, material);
  scene.add(currentObject);
}

function loadGLB(url) {
  clearObject();
  const loader = new THREE.GLTFLoader();
  loader.load(url, gltf => {
    currentObject = gltf.scene;
    currentObject.scale.set(1, 1, 1);
    scene.add(currentObject);
  }, undefined, () => {
    alert('GLB 파일을 찾지 못했습니다. 샘플 도형으로 대체합니다.');
    showSample();
  });
}

document.getElementById('sampleBtn').addEventListener('click', showSample);
document.getElementById('loadModelBtn').addEventListener('click', () => loadGLB(document.getElementById('modelUrl').value));
window.addEventListener('resize', () => {
  if (!renderer || !camera) return;
  camera.aspect = wrap.clientWidth / wrap.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(wrap.clientWidth, wrap.clientHeight || 420);
});
initScene();
showSample();
