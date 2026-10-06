(function (root) {
    function rotateAxis(axis, rotation, THREE) {
        return new THREE.Vector3(...axis)
            .applyQuaternion(rotation)
            .normalize()
            .toArray()
            .map(value => Math.abs(value) < 1e-10 ? 0 : Number(value.toFixed(6)));
    }

    function alignToWorld(worldFrame, jointAxis, THREE, axisCandidates = [], rootWorldFrame = null) {
        const rootToWorld = rootWorldFrame
            ? rootWorldFrame.clone()
            : new THREE.Matrix4();
        const sceneWorldFrame = rootToWorld.clone().multiply(worldFrame);
        const position = new THREE.Vector3();
        const rotation = new THREE.Quaternion();
        const scale = new THREE.Vector3();
        sceneWorldFrame.decompose(position, rotation, scale);

        const localAxis = new THREE.Vector3(...jointAxis);
        if (localAxis.lengthSq() === 0) localAxis.set(0, 0, 1);
        localAxis.normalize();
        const worldAxis = localAxis.clone().applyQuaternion(rotation).normalize();

        // Preserve the physical joint axis and use the remaining degree of
        // freedom (twist about that axis) to bring the frame as close as
        // possible to world XYZ. For oblique axes exact parallelism is
        // impossible, so minimize the total angular mismatch of the frame.
        let cosineTerm = 0;
        let sineTerm = 0;
        for (let index = 0; index < 3; index += 1) {
            const localBasis = new THREE.Vector3(
                index === 0 ? 1 : 0,
                index === 1 ? 1 : 0,
                index === 2 ? 1 : 0
            );
            const currentWorldBasis = localBasis.applyQuaternion(rotation);
            const desiredWorldBasis = new THREE.Vector3(
                index === 0 ? 1 : 0,
                index === 1 ? 1 : 0,
                index === 2 ? 1 : 0
            );
            cosineTerm += currentWorldBasis.dot(desiredWorldBasis)
                - worldAxis.dot(currentWorldBasis) * worldAxis.dot(desiredWorldBasis);
            sineTerm += worldAxis.clone().cross(currentWorldBasis).dot(desiredWorldBasis);
        }
        const twistAngle = Math.hypot(cosineTerm, sineTerm) > 1e-12
            ? Math.atan2(sineTerm, cosineTerm)
            : 0;
        const alignedRotation = new THREE.Quaternion()
            .setFromAxisAngle(worldAxis, twistAngle)
            .multiply(rotation)
            .normalize();

        const alignedSceneFrame = new THREE.Matrix4().compose(
            position,
            alignedRotation,
            scale
        );
        // The editor stores joint frames relative to robotRoot, but the helper
        // is rendered in scene world. Convert the corrected frame back to the
        // storage frame without changing its world position.
        const alignedFrame = rootToWorld.invert().multiply(alignedSceneFrame);

        const inverseAlignedRotation = alignedRotation.clone().invert();
        const transformedCandidates = axisCandidates.map(candidate => {
            const candidateWorldAxis = new THREE.Vector3(...candidate.axis)
                .applyQuaternion(rotation);
            return {
                ...candidate,
                axis: rotateAxis(candidateWorldAxis.toArray(), inverseAlignedRotation, THREE),
            };
        });
        return {
            frame: alignedFrame,
            axis: localAxis.toArray(),
            axisCandidates: transformedCandidates,
        };
    }

    const api = {alignToWorld};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    root.PetasosJointZeroFrame = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
