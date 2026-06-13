(function () {
  'use strict';

  // ---------- Configuration ----------
  const GRAVITY = -65;
  const JUMP_VELOCITY = 24;
  const DINO_Z = 6;
  const SPAWN_Z = 80;
  const DESPAWN_Z = -12;
  const BASE_SPEED = 14;

  // ---------- DOM ----------
  const canvas = document.getElementById('game-canvas');
  const scoreEl = document.getElementById('score');
  const highScoreEl = document.getElementById('high-score');
  const messageEl = document.getElementById('message');
  const gameOverEl = document.getElementById('game-over');
  const startBtn = document.getElementById('start-btn');
  const restartBtn = document.getElementById('restart-btn');
  const scoreBoard = document.getElementById('score-board');

  // ---------- State ----------
  let scene, camera, renderer;
  let dino, ground, groundTexture, horizonLine;
  let obstacles = [];
  let clouds = [];
  let gameState = 'start'; // start | playing | over
  let score = 0;
  let highScore = 0;
  let speed = BASE_SPEED;
  let distance = 0;
  let isNight = false;
  let lastTime = 0;
  let spawnTimer = 0;
  let nextSpawn = 1.5;
  let ducking = false;
  let dinoY = 0;
  let dinoVy = 0;
  let onGround = true;

  // Camera orbit state
  const CAMERA_RADIUS = 22;
  const CAMERA_HEIGHT = 7;
  let cameraAngle = Math.PI / 4;
  let isDragging = false;
  let pointerDownX = 0;
  let pointerDownY = 0;
  let pointerCurrentX = 0;
  let pointerCurrentY = 0;
  let pointerDownTime = 0;
  const DRAG_THRESHOLD = 10;

  // ---------- Init ----------
  function init() {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xffffff);
    scene.fog = new THREE.Fog(0xffffff, 40, 160);

    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 300);
    updateCamera();

    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    setupLights();
    createGround();
    createHorizon();
    createDino();
    createClouds();

    window.addEventListener('resize', onResize);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('keyup', onKeyUp);
    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerUp);
    startBtn.addEventListener('click', startGame);
    restartBtn.addEventListener('click', resetGame);

    highScore = parseInt(localStorage.getItem('dino3d_highscore') || '0', 10);
    updateScoreUI();

    requestAnimationFrame(loop);
  }

  function setupLights() {
    scene.userData.hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 0.85);
    scene.add(scene.userData.hemi);

    scene.userData.dir = new THREE.DirectionalLight(0xffffff, 0.9);
    scene.userData.dir.position.set(30, 50, 30);
    scene.userData.dir.castShadow = true;
    scene.userData.dir.shadow.mapSize.set(2048, 2048);
    scene.userData.dir.shadow.camera.left = -50;
    scene.userData.dir.shadow.camera.right = 50;
    scene.userData.dir.shadow.camera.top = 50;
    scene.userData.dir.shadow.camera.bottom = -50;
    scene.add(scene.userData.dir);
  }

  function createGround() {
    const geometry = new THREE.PlaneGeometry(300, 300);
    const material = new THREE.MeshStandardMaterial({ color: 0xf7f7f7, roughness: 0.9 });
    ground = new THREE.Mesh(geometry, material);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    const texCanvas = document.createElement('canvas');
    texCanvas.width = 512;
    texCanvas.height = 512;
    const ctx = texCanvas.getContext('2d');
    ctx.fillStyle = '#f7f7f7';
    ctx.fillRect(0, 0, 512, 512);
    ctx.fillStyle = '#e0e0e0';
    for (let i = 0; i < 500; i++) {
      const x = Math.random() * 512;
      const y = Math.random() * 512;
      const s = Math.random() * 2 + 1;
      ctx.fillRect(x, y, s, s);
    }
    ctx.strokeStyle = '#dddddd';
    ctx.lineWidth = 2;
    for (let i = 0; i < 512; i += 64) {
      ctx.beginPath();
      ctx.moveTo(0, i);
      ctx.lineTo(512, i);
      ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(texCanvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(30, 30);
    texture.magFilter = THREE.NearestFilter;
    ground.material.map = texture;
    groundTexture = texture;
  }

  function createHorizon() {
    const geometry = new THREE.PlaneGeometry(300, 0.15);
    const material = new THREE.MeshBasicMaterial({ color: 0x535353 });
    horizonLine = new THREE.Mesh(geometry, material);
    horizonLine.position.set(0, 0.08, -40);
    horizonLine.rotation.x = -Math.PI / 2;
    scene.add(horizonLine);
  }

  function createDino() {
    dino = new THREE.Group();
    dino.position.set(0, 0, DINO_Z);

    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x535353, roughness: 0.7 });
    const eyeMat = new THREE.MeshStandardMaterial({ color: 0xffffff });

    const body = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.7, 2.4), bodyMat);
    body.position.y = 1.6;
    body.castShadow = true;
    dino.add(body);

    const head = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.2, 1.6), bodyMat);
    head.position.set(0, 2.9, 1.2);
    head.castShadow = true;
    dino.add(head);

    const eye = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.1), eyeMat);
    eye.position.set(0.3, 3.05, 2.0);
    dino.add(eye);

    const tail = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.6, 1.5), bodyMat);
    tail.position.set(0, 1.4, -1.7);
    tail.rotation.x = -0.3;
    tail.castShadow = true;
    dino.add(tail);

    const legGeo = new THREE.BoxGeometry(0.5, 1.2, 0.6);
    dino.userData.leftLeg = new THREE.Mesh(legGeo, bodyMat);
    dino.userData.leftLeg.position.set(-0.5, 0.6, -0.3);
    dino.userData.leftLeg.castShadow = true;
    dino.add(dino.userData.leftLeg);

    dino.userData.rightLeg = new THREE.Mesh(legGeo, bodyMat);
    dino.userData.rightLeg.position.set(0.5, 0.6, 0.3);
    dino.userData.rightLeg.castShadow = true;
    dino.add(dino.userData.rightLeg);

    const armGeo = new THREE.BoxGeometry(0.3, 0.8, 0.3);
    dino.userData.leftArm = new THREE.Mesh(armGeo, bodyMat);
    dino.userData.leftArm.position.set(-0.85, 2.0, 0.6);
    dino.userData.leftArm.rotation.x = 0.5;
    dino.add(dino.userData.leftArm);

    dino.userData.rightArm = new THREE.Mesh(armGeo, bodyMat);
    dino.userData.rightArm.position.set(0.85, 2.0, 0.6);
    dino.userData.rightArm.rotation.x = 0.5;
    dino.add(dino.userData.rightArm);

    scene.add(dino);
  }

  function createClouds() {
    const cloudMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.85,
      flatShading: true
    });
    for (let i = 0; i < 10; i++) {
      const cloud = new THREE.Group();
      const chunks = 3 + Math.floor(Math.random() * 3);
      for (let j = 0; j < chunks; j++) {
        const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), cloudMat);
        mesh.position.set(
          (Math.random() - 0.5) * 4,
          (Math.random() - 0.5) * 1.5,
          (Math.random() - 0.5) * 2.5
        );
        mesh.scale.set(1.5 + Math.random() * 2.5, 1 + Math.random(), 1 + Math.random() * 1.5);
        cloud.add(mesh);
      }
      cloud.position.set(
        (Math.random() - 0.5) * 100,
        14 + Math.random() * 10,
        -30 - Math.random() * 100
      );
      scene.add(cloud);
      clouds.push({ mesh: cloud, speed: 2 + Math.random() * 4 });
    }
  }

  // ---------- Obstacles ----------
  function spawnObstacle() {
    const type = Math.random() < 0.7 ? 'cactus' : 'bird';
    const group = new THREE.Group();
    group.position.z = SPAWN_Z;

    // Obstacles now spawn ahead of the dino and run toward it (-Z direction)
    if (type === 'cactus') {
      const mat = new THREE.MeshStandardMaterial({ color: 0x535353, roughness: 0.8 });
      const size = Math.random() < 0.5 ? 'small' : 'large';
      const height = size === 'small' ? 1.6 : 2.6;
      const width = size === 'small' ? 0.45 : 0.65;
      const count = 1 + Math.floor(Math.random() * 3);
      for (let i = 0; i < count; i++) {
        const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, width), mat);
        mesh.position.set(
          (i - (count - 1) / 2) * 1.0 + (Math.random() - 0.5) * 0.3,
          height / 2,
          0
        );
        mesh.castShadow = true;
        group.add(mesh);
      }
      group.userData.type = 'cactus';
    } else {
      const mat = new THREE.MeshStandardMaterial({ color: 0x535353, roughness: 0.8 });
      const body = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.4, 0.6), mat);
      body.position.y = 1.2;
      body.castShadow = true;
      group.add(body);

      const wingL = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.1, 0.45), mat);
      wingL.position.set(-0.75, 1.45, 0);
      wingL.name = 'wingL';
      group.add(wingL);

      const wingR = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.1, 0.45), mat);
      wingR.position.set(0.75, 1.45, 0);
      wingR.name = 'wingR';
      group.add(wingR);

      // Birds always fly high so mobile players don't need to duck
      group.position.y = 2.4 + Math.random() * 0.5;
      group.userData.type = 'bird';
    }

    scene.add(group);
    obstacles.push(group);
  }

  // ---------- Game flow ----------
  function startGame() {
    if (gameState === 'playing') return;
    resetGameVars();
    gameState = 'playing';
    messageEl.classList.add('hidden');
    gameOverEl.classList.add('hidden');
  }

  function resetGame() {
    resetGameVars();
    gameState = 'playing';
    gameOverEl.classList.add('hidden');
    messageEl.classList.add('hidden');
  }

  function resetGameVars() {
    obstacles.forEach(o => scene.remove(o));
    obstacles = [];
    score = 0;
    distance = 0;
    speed = BASE_SPEED;
    dinoY = 0;
    dinoVy = 0;
    onGround = true;
    ducking = false;
    spawnTimer = 0;
    nextSpawn = 1.2 + Math.random();
    updateScoreUI();
    if (isNight) setTheme(false);
  }

  function gameOver() {
    gameState = 'over';
    if (score > highScore) {
      highScore = Math.floor(score);
      localStorage.setItem('dino3d_highscore', highScore.toString());
    }
    updateScoreUI();
    gameOverEl.classList.remove('hidden');
  }

  function updateScoreUI() {
    scoreEl.textContent = Math.floor(score).toString().padStart(5, '0');
    highScoreEl.textContent = 'HI ' + highScore.toString().padStart(5, '0');
  }

  // ---------- Controls ----------
  function jump() {
    if (gameState === 'start') {
      startGame();
      return;
    }
    if (gameState === 'over') {
      resetGame();
      return;
    }
    if (onGround) {
      dinoVy = JUMP_VELOCITY;
      onGround = false;
      ducking = false;
    }
  }

  function duck(active) {
    if (gameState !== 'playing') return;
    ducking = active;
  }

  function onKeyDown(e) {
    if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW') {
      e.preventDefault();
      jump();
    } else if (e.code === 'ArrowDown' || e.code === 'KeyS') {
      e.preventDefault();
      duck(true);
    }
  }

  function onKeyUp(e) {
    if (e.code === 'ArrowDown' || e.code === 'KeyS') {
      duck(false);
    }
  }

  function updateCamera() {
    if (!camera) return;
    camera.position.x = CAMERA_RADIUS * Math.sin(cameraAngle);
    camera.position.z = DINO_Z + CAMERA_RADIUS * Math.cos(cameraAngle);
    camera.position.y = CAMERA_HEIGHT;
    camera.lookAt(0, 2.5, DINO_Z);
  }

  function onPointerDown(e) {
    if (e.target.tagName === 'BUTTON') return;
    isDragging = true;
    pointerDownX = e.clientX;
    pointerDownY = e.clientY;
    pointerCurrentX = e.clientX;
    pointerCurrentY = e.clientY;
    pointerDownTime = performance.now();
    try {
      canvas.setPointerCapture(e.pointerId);
    } catch (_) {}
  }

  function onPointerMove(e) {
    if (!isDragging) return;
    const dx = e.clientX - pointerCurrentX;
    pointerCurrentX = e.clientX;
    pointerCurrentY = e.clientY;
    cameraAngle -= dx * 0.006;
    updateCamera();
  }

  function onPointerUp(e) {
    if (!isDragging) return;
    isDragging = false;
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch (_) {}
    const dx = pointerCurrentX - pointerDownX;
    const dy = pointerCurrentY - pointerDownY;
    const dist = Math.hypot(dx, dy);
    const dt = performance.now() - pointerDownTime;
    if (dist < DRAG_THRESHOLD && dt < 300) {
      jump();
    }
  }

  function onResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  }

  // ---------- Theme ----------
  function setTheme(night) {
    isNight = night;
    if (night) {
      scene.background.setHex(0x202124);
      scene.fog.color.setHex(0x202124);
      ground.material.color.setHex(0x2a2a2a);
      horizonLine.material.color.setHex(0xe0e0e0);
      scene.userData.hemi.intensity = 0.3;
      scene.userData.dir.intensity = 0.3;
      scoreBoard.classList.add('night');
      messageEl.classList.add('night');
      gameOverEl.classList.add('night');
    } else {
      scene.background.setHex(0xffffff);
      scene.fog.color.setHex(0xffffff);
      ground.material.color.setHex(0xf7f7f7);
      horizonLine.material.color.setHex(0x535353);
      scene.userData.hemi.intensity = 0.85;
      scene.userData.dir.intensity = 0.9;
      scoreBoard.classList.remove('night');
      messageEl.classList.remove('night');
      gameOverEl.classList.remove('night');
    }
  }

  // ---------- Update ----------
  function update(dt) {
    // Cloud drift (always)
    clouds.forEach(c => {
      c.mesh.position.z += c.speed * dt;
      if (c.mesh.position.z > 20) {
        c.mesh.position.z = -100 - Math.random() * 60;
        c.mesh.position.x = (Math.random() - 0.5) * 100;
      }
    });

    // Idle leg sway
    if (gameState !== 'playing' && dino) {
      const t = performance.now() * 0.005;
      dino.userData.leftLeg.rotation.x = Math.sin(t) * 0.15;
      dino.userData.rightLeg.rotation.x = Math.sin(t + Math.PI) * 0.15;
      return;
    }

    if (gameState !== 'playing') return;

    speed = BASE_SPEED + Math.floor(distance / 180) * 1.2;

    // Jump physics
    if (!onGround) {
      if (ducking) dinoVy = Math.min(dinoVy, -10);
      dinoVy += GRAVITY * dt;
      dinoY += dinoVy * dt;
      if (dinoY <= 0) {
        dinoY = 0;
        dinoVy = 0;
        onGround = true;
      }
    }

    // Duck shape
    if (ducking && onGround) {
      dino.scale.y = 0.55;
    } else {
      dino.scale.y = 1;
    }
    dino.position.y = dinoY;

    // Run animation
    const runFreq = distance * speed * 0.08;
    dino.userData.leftLeg.rotation.x = Math.sin(runFreq) * 0.9;
    dino.userData.rightLeg.rotation.x = Math.sin(runFreq + Math.PI) * 0.9;
    dino.userData.leftArm.rotation.x = 0.5 + Math.sin(runFreq) * 0.3;
    dino.userData.rightArm.rotation.x = 0.5 + Math.sin(runFreq + Math.PI) * 0.3;

    // Scroll ground (opposite to running direction)
    distance += speed * dt;
    if (groundTexture) {
      groundTexture.offset.y += (speed * dt) / 300;
    }

    // Spawn
    spawnTimer += dt;
    if (spawnTimer >= nextSpawn) {
      spawnObstacle();
      spawnTimer = 0;
      nextSpawn = Math.max(0.55, 1.0 + Math.random() * 1.2 - Math.min(0.6, distance / 2000));
    }

    // Hitbox
    const dinoBox = new THREE.Box3().setFromObject(dino).expandByScalar(-0.25);

    // Move obstacles
    for (let i = obstacles.length - 1; i >= 0; i--) {
      const obs = obstacles[i];
      obs.position.z -= speed * dt;

      if (obs.userData.type === 'bird') {
        const t = performance.now() * 0.015;
        obs.getObjectByName('wingL').rotation.z = 0.3 + Math.sin(t) * 0.5;
        obs.getObjectByName('wingR').rotation.z = -0.3 - Math.sin(t) * 0.5;
      }

      const obsBox = new THREE.Box3().setFromObject(obs).expandByScalar(-0.1);
      if (dinoBox.intersectsBox(obsBox)) {
        gameOver();
      }

      if (obs.position.z < DESPAWN_Z) {
        scene.remove(obs);
        obstacles.splice(i, 1);
      }
    }

    score += speed * dt * 0.12;
    updateScoreUI();

    // Day/night cycle every 800 points
    const night = Math.floor(score / 800) % 2 === 1;
    if (night !== isNight) setTheme(night);
  }

  function loop(time) {
    const dt = Math.min((time - lastTime) / 1000, 0.06);
    lastTime = time;
    update(dt);
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  }

  // ---------- PWA Service Worker ----------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./service-worker.js', { scope: './' })
        .then(reg => console.log('[DinoPWA] Service worker registered:', reg.scope))
        .catch(err => console.error('[DinoPWA] Service worker registration failed:', err));
    });
  }

  init();
})();
