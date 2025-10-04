import * as THREE from 'three';
import { UnifiedTrackingResult, SceneState } from './types';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';

// Fixed local Z-axis offset for STL models (-90 degrees)
const STL_Z_OFFSET = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -Math.PI / 2);

// Helper function to extract position and quaternion from 4x4 matrix (column-major)
const extractPoseFromMatrix = (matrix: number[]) => {
    // Matrix is column-major: [m0,m1,m2,m3, m4,m5,m6,m7, m8,m9,m10,m11, m12,m13,m14,m15]
    // Position is in the 4th column: [m12, m13, m14]
    const position = new THREE.Vector3(matrix[12], matrix[13], matrix[14]);
    
    // Create rotation matrix from first 3 columns
    const rotMatrix = new THREE.Matrix4();
    rotMatrix.set(
        matrix[0], matrix[4], matrix[8],  matrix[12],
        matrix[1], matrix[5], matrix[9],  matrix[13],
        matrix[2], matrix[6], matrix[10], matrix[14],
        matrix[3], matrix[7], matrix[11], matrix[15]
    );
    
    const quaternion = new THREE.Quaternion();
    quaternion.setFromRotationMatrix(rotMatrix);
    
    return { position, quaternion };
};

// Update STL mesh positions based on hand tracking
export const updateSTLPositions = (sceneState: SceneState, trackingResult: UnifiedTrackingResult) => {
    if (!sceneState.scene) return;
    const isController = trackingResult.left?.trigger !== undefined || trackingResult.right?.trigger !== undefined;
    
    // Add meshes to scene if they exist but aren't added yet
    if (sceneState.leftHandMesh && !sceneState.scene.children.includes(sceneState.leftHandMesh)) {
        sceneState.scene.add(sceneState.leftHandMesh);
    }
    if (sceneState.rightHandMesh && !sceneState.scene.children.includes(sceneState.rightHandMesh)) {
        sceneState.scene.add(sceneState.rightHandMesh);
    }

    // Update left hand mesh
    if (trackingResult.left && sceneState.leftHandMesh) {
        const { position, quaternion } = extractPoseFromMatrix(trackingResult.left.targetLocation);
        
        sceneState.leftHandMesh.position.copy(position);
        sceneState.leftHandMesh.quaternion.copy(quaternion);
        
        // Apply persistent 90° rotation about the mesh's own Z axis for controllers
        if (isController) {
            sceneState.leftHandMesh.quaternion.multiply(STL_Z_OFFSET);
        }
        sceneState.leftHandMesh.visible = true;
    } else if (sceneState.leftHandMesh) {
        sceneState.leftHandMesh.visible = false;
    }

    // Update right hand mesh
    if (trackingResult.right && sceneState.rightHandMesh) {
        const { position, quaternion } = extractPoseFromMatrix(trackingResult.right.targetLocation);
        
        sceneState.rightHandMesh.position.copy(position);
        sceneState.rightHandMesh.quaternion.copy(quaternion);
        
        // Apply persistent 90° rotation about the mesh's own Z axis for controllers
        if (isController) {
            sceneState.rightHandMesh.quaternion.multiply(STL_Z_OFFSET);
        }
        sceneState.rightHandMesh.visible = true;
    } else if (sceneState.rightHandMesh) {
        sceneState.rightHandMesh.visible = false;
    }

    // Hide meshes if no tracking data
    if (!trackingResult.left && !trackingResult.right) {
        if (sceneState.leftHandMesh) sceneState.leftHandMesh.visible = false;
        if (sceneState.rightHandMesh) sceneState.rightHandMesh.visible = false;
    }
};

// Load STL models for hand tracking
export const loadSTLModels = async (sceneState: SceneState) => {
    return new Promise((resolve, reject) => {
        const loader = new STLLoader();

        console.log('Starting STL model loading...');

        // Check available memory (rough estimate)
        if ('memory' in performance) {
            const memory = (performance as any).memory;
            console.log('Browser memory info:', {
                used: (memory.usedJSHeapSize / 1024 / 1024).toFixed(2) + ' MB',
                total: (memory.totalJSHeapSize / 1024 / 1024).toFixed(2) + ' MB',
                limit: (memory.jsHeapSizeLimit / 1024 / 1024).toFixed(2) + ' MB'
            });
        }

        // Load STL file
        loader.load(
            '/prt0001.stl', // Path to STL file
            (geometry) => {
                try {
                    console.log('STL geometry loaded successfully');
                    console.log('Geometry attributes:', Object.keys(geometry.attributes));

                    // Check geometry size
                    const positionAttr = geometry.getAttribute('position');
                    if (positionAttr) {
                        console.log('Position array length:', positionAttr.count);
                        console.log('Position array size (MB):', (positionAttr.array.byteLength / 1024 / 1024).toFixed(2));

                        // Check if geometry is too large (>50MB or >1M vertices)
                        const sizeMB = positionAttr.array.byteLength / 1024 / 1024;
                        const vertexCount = positionAttr.count;

                        if (sizeMB > 50 || vertexCount > 1000000) {
                            console.warn('STL file is very large, consider optimizing:', {
                                sizeMB: sizeMB.toFixed(2),
                                vertexCount: vertexCount
                            });

                            // Optionally simplify geometry for very large files
                            // Note: This might not be available in all Three.js versions
                            if (geometry.computeBoundingBox) {
                                geometry.computeBoundingBox();
                                console.log('Bounding box:', geometry.boundingBox);
                            }
                        }
                    }

                    // Create separate materials for each hand to avoid color sharing
                    const leftMaterial = new THREE.MeshLambertMaterial({
                        color: 0x888888, // Gray color
                        side: THREE.DoubleSide
                    });

                    const rightMaterial = new THREE.MeshLambertMaterial({
                        color: 0x888888, // Gray color
                        side: THREE.DoubleSide
                    });

                    // Create left and right hand meshes with separate materials
                    const leftMesh = new THREE.Mesh(geometry, leftMaterial);
                    const rightMesh = new THREE.Mesh(geometry, rightMaterial);

                    // Scale to make the largest dimension about 0.1 units (adjustable)
                    const scale = 1

                    // Apply scale and flip on all axes
                    leftMesh.scale.set(scale, scale, -scale);
                    rightMesh.scale.set(scale, scale, -scale);

                    // Initially hide meshes
                    leftMesh.visible = false;
                    rightMesh.visible = false;

                    sceneState.leftHandMesh = leftMesh;
                    sceneState.rightHandMesh = rightMesh;

                    // Add to scene if it exists
                    if (sceneState.scene) {
                        sceneState.scene.add(leftMesh);
                        sceneState.scene.add(rightMesh);
                        console.log('STL meshes added to scene successfully');
                        resolve(true);
                    } else {
                        reject(new Error('no scene ref for stl'));
                    }
                } catch (error) {
                    console.error('Error processing STL geometry:', error);
                    reject(error);
                }
            },
            (progress) => {
                // Progress callback
                console.log('STL loading progress:', progress);
            },
            (error) => {
                console.error('Error loading STL file:', error);

                // Type-safe error handling
                const errorObj = error as Error;
                console.error('Error details:', {
                    message: errorObj.message,
                    stack: errorObj.stack,
                    name: errorObj.name
                });

                // Provide more helpful error messages
                if (errorObj.message && errorObj.message.includes('array')) {
                    console.error('STL parsing error likely due to large file size or memory limitations');
                    console.error('Suggestions:');
                    console.error('1. Check if the STL file is corrupted');
                    console.error('2. Try reducing the STL file complexity');
                    console.error('3. Check browser memory limits');
                    console.error('4. Try refreshing the page');
                }

                reject(error);
            }
        );
    });
};

// Alternative STL loading with error recovery
export const loadSTLModelsWithFallback = async (sceneState: SceneState) => {
    try {
        console.log('Attempting to load STL models...');
        await loadSTLModels(sceneState);
    } catch (error) {
        console.error('Primary STL loading failed, attempting fallback...');

        // Create simple fallback geometry (a small cube)
        const fallbackGeometry = new THREE.BoxGeometry(0.01, 0.01, 0.01);

        const leftMaterial = new THREE.MeshLambertMaterial({
            color: 0xff0000, // Red to indicate fallback
            side: THREE.DoubleSide
        });

        const rightMaterial = new THREE.MeshLambertMaterial({
            color: 0x00ff00, // Green to indicate fallback
            side: THREE.DoubleSide
        });

        const leftMesh = new THREE.Mesh(fallbackGeometry, leftMaterial);
        const rightMesh = new THREE.Mesh(fallbackGeometry, rightMaterial);

        leftMesh.visible = false;
        rightMesh.visible = false;

        sceneState.leftHandMesh = leftMesh;
        sceneState.rightHandMesh = rightMesh;

        if (sceneState.scene) {
            sceneState.scene.add(leftMesh);
            sceneState.scene.add(rightMesh);
            console.log('Fallback STL meshes (cubes) added successfully');
        }
    }
};