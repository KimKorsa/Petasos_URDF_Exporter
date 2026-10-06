(function (root) {
    function vector(values, THREE) {
        if (!Array.isArray(values) || values.length !== 3 || !values.every(Number.isFinite)) {
            return null;
        }
        return new THREE.Vector3(...values);
    }

    function connectorFrame(connector, preferredXAxis, THREE) {
        const point = vector(connector && connector.point, THREE);
        const normal = vector(connector && connector.normal, THREE);
        if (!point || !normal || normal.lengthSq() < 1e-12) return null;

        const zAxis = normal.normalize();
        const tangent = vector(connector.tangent, THREE);
        const preferred = vector(preferredXAxis, THREE);
        const xAxis = tangent || preferred || new THREE.Vector3(1, 0, 0);
        xAxis.addScaledVector(zAxis, -xAxis.dot(zAxis));
        if (xAxis.lengthSq() < 1e-10) {
            const candidates = [
                new THREE.Vector3(1, 0, 0),
                new THREE.Vector3(0, 1, 0),
                new THREE.Vector3(0, 0, 1),
            ].sort((a, b) => Math.abs(a.dot(zAxis)) - Math.abs(b.dot(zAxis)));
            xAxis.copy(candidates[0]).addScaledVector(
                zAxis,
                -candidates[0].dot(zAxis)
            );
        }
        xAxis.normalize();
        const yAxis = new THREE.Vector3().crossVectors(zAxis, xAxis).normalize();
        xAxis.crossVectors(yAxis, zAxis).normalize();
        return new THREE.Matrix4().makeBasis(xAxis, yAxis, zAxis).setPosition(point);
    }

    function build(THREE, parent, child, preferredXAxis = null, jointMotion = {}) {
        if (!THREE || !THREE.Matrix4 || !THREE.Vector3 || !parent || !child) return null;
        const parentFrame = connectorFrame(parent, preferredXAxis, THREE);
        const childFrame = connectorFrame(child, preferredXAxis, THREE);
        if (!parentFrame || !childFrame) return null;

        // Mating faces face each other: preserve connector X and reverse Y/Z.
        // Counter the currently previewed joint motion in the neutral child
        // frame so rebuilding the rig does not pull the newly mated faces apart.
        const inverseMotion = new THREE.Matrix4();
        const jointValue = Number(jointMotion.value) || 0;
        if (jointMotion.type === 'prismatic') {
            const unitsPerMeter = Number(jointMotion.unitsPerMeter) || 1;
            inverseMotion.makeTranslation(0, 0, -jointValue * unitsPerMeter);
        } else if (jointMotion.type === 'revolute' || jointMotion.type === 'continuous') {
            inverseMotion.makeRotationZ(-jointValue);
        }
        const rollFrame = Number(jointMotion.roll) === 1
            ? new THREE.Matrix4().makeRotationZ(Math.PI)
            : new THREE.Matrix4();
        const childFacingParent = parentFrame.clone()
            .multiply(inverseMotion)
            .multiply(rollFrame)
            .multiply(new THREE.Matrix4().makeRotationX(Math.PI));
        const childDelta = childFacingParent.clone().multiply(
            childFrame.clone().invert()
        );
        return {
            jointFrame: parentFrame,
            childDelta,
            xAxis: new THREE.Vector3().setFromMatrixColumn(parentFrame, 0).normalize(),
            yAxis: new THREE.Vector3().setFromMatrixColumn(parentFrame, 1).normalize(),
            zAxis: new THREE.Vector3().setFromMatrixColumn(parentFrame, 2).normalize(),
            orthogonalityError: 0,
        };
    }

    const api = {build};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    root.PetasosJointMateAlignment = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
