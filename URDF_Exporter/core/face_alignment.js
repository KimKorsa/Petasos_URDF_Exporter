(function (root) {
    'use strict';

    function validateFacePair(first, second) {
        if (!first || !second || !first.linkId || !second.linkId) {
            return { ok: false, reason: 'missing_link' };
        }
        if (first.linkId === second.linkId) {
            return { ok: false, reason: 'same_link' };
        }
        if (Array.isArray(second.subtreeLinkIds) && second.subtreeLinkIds.includes(first.linkId)) {
            return { ok: false, reason: 'fixed_face_in_moving_subtree' };
        }
        return { ok: true, reason: '' };
    }

    function normalizeFacePair(first, second) {
        if (!first || !second || !first.linkId || !second.linkId) {
            return { ok: false, reason: 'missing_link' };
        }
        if (first.linkId === second.linkId) {
            return { ok: false, reason: 'same_link' };
        }
        let reference = first;
        let moving = second;
        let swapped = false;
        if (Array.isArray(second.subtreeLinkIds) && second.subtreeLinkIds.includes(first.linkId)) {
            reference = second;
            moving = first;
            swapped = true;
        }
        const validation = validateFacePair(reference, moving);
        if (!validation.ok) return validation;
        return { ok: true, reference, moving, swapped };
    }

    function getFaceParallelNormalMode(tree) {
        return tree && ['same', 'opposed'].includes(tree._face_parallel_normal_mode)
            ? tree._face_parallel_normal_mode
            : 'opposed';
    }

    function setFaceParallelNormalMode(tree, mode) {
        if (!tree || !['same', 'opposed'].includes(mode)) return false;
        tree._face_parallel_normal_mode = mode;
        return true;
    }

    function buildPlanarFaceOverlayGeometry(THREE, sourceGeometry, triangleIndices) {
        if (!THREE || !sourceGeometry || !Array.isArray(triangleIndices)) return null;
        const position = sourceGeometry.getAttribute
            ? sourceGeometry.getAttribute('position')
            : sourceGeometry.attributes && sourceGeometry.attributes.position;
        if (!position) return null;
        const sourceIndex = sourceGeometry.index;
        const slotCount = sourceIndex ? sourceIndex.count : position.count;
        const vertices = [];
        triangleIndices.forEach(triangleIndex => {
            const base = Number(triangleIndex) * 3;
            if (!Number.isInteger(Number(triangleIndex)) || base < 0 || base + 2 >= slotCount) return;
            for (let corner = 0; corner < 3; corner += 1) {
                const slot = base + corner;
                const vertexIndex = sourceIndex ? sourceIndex.getX(slot) : slot;
                vertices.push(position.getX(vertexIndex), position.getY(vertexIndex), position.getZ(vertexIndex));
            }
        });
        if (!vertices.length) return null;
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        geometry.computeVertexNormals();
        geometry.computeBoundingBox();
        geometry.computeBoundingSphere();
        return geometry;
    }

    function buildFaceParallelDelta(
        THREE,
        referenceNormalValues,
        movingNormalValues,
        pivotValues,
        normalMode = 'opposed'
    ) {
        if (!THREE || !Array.isArray(referenceNormalValues)
            || !Array.isArray(movingNormalValues) || !Array.isArray(pivotValues)) return null;

        const referenceNormal = new THREE.Vector3().fromArray(referenceNormalValues);
        const movingNormal = new THREE.Vector3().fromArray(movingNormalValues);
        const pivot = new THREE.Vector3().fromArray(pivotValues);
        if (
            ![...referenceNormalValues, ...movingNormalValues, ...pivotValues].every(Number.isFinite)
            || referenceNormal.lengthSq() < 1e-12
            || movingNormal.lengthSq() < 1e-12
        ) return null;

        referenceNormal.normalize();
        movingNormal.normalize();
        const targetNormal = normalMode === 'same'
            ? referenceNormal
            : referenceNormal.clone().negate();
        const rotation = new THREE.Quaternion().setFromUnitVectors(
            movingNormal,
            targetNormal
        ).normalize();
        const matrix = new THREE.Matrix4().makeTranslation(pivot.x, pivot.y, pivot.z)
            .multiply(new THREE.Matrix4().makeRotationFromQuaternion(rotation))
            .multiply(new THREE.Matrix4().makeTranslation(-pivot.x, -pivot.y, -pivot.z));
        return { matrix: matrix.toArray(), rotation: rotation.toArray(), pivot: pivot.toArray() };
    }

    function deltaInNeutralParentFrame(THREE, rootDelta, parentCurrentRoot, parentNeutralRoot) {
        if (!THREE || !rootDelta || !parentCurrentRoot || !parentNeutralRoot) return null;
        const parentMotion = parentCurrentRoot.clone()
            .multiply(parentNeutralRoot.clone().invert());
        return parentMotion.clone().invert()
            .multiply(rootDelta)
            .multiply(parentMotion);
    }

    const api = {
        buildFaceParallelDelta,
        buildPlanarFaceOverlayGeometry,
        deltaInNeutralParentFrame,
        getFaceParallelNormalMode,
        normalizeFacePair,
        setFaceParallelNormalMode,
        validateFacePair,
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (root) root.PetasosFaceAlignment = api;
})(typeof window !== 'undefined' ? window : globalThis);
