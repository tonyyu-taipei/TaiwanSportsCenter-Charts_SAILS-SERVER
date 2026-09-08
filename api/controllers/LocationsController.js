/**
 * LocationsController
 *
 * @description :: Server-side actions for handling incoming requests.
 * @help        :: See https://sailsjs.com/docs/concepts/actions
 */

module.exports = {

    find: async function (req, res) {
        try {
            const locations = await Locations.find();
            return res.locations();
        } catch (err) {
            return res.serverError(err);
        }
    }
};

