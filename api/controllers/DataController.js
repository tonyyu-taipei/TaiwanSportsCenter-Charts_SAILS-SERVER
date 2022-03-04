/**
 * DataController
 *
 * @description :: Server-side actions for handling incoming requests.
 * @help        :: See https://sailsjs.com/docs/concepts/actions
 */

//const Data = require("../models/Data");
const { isSameDay } = require('date-fns')
function dateFilter(input,params){ // import the object from the database and the request.
  let resultObj = []
  let reqTime = new Date(params);

  input.forEach(data => {
    let dataTime = new Date(data.time)
    if(isSameDay(reqTime,dataTime)){
      resultObj.push(data);
    }

  })

  return resultObj
}
module.exports = {
  Date: async function(req,res){
    Data.find({}).exec((err,result)=>{
      if(req.param('date'))
        res.send(dateFilter(result,req.param('date')))
      else{
      if(err)res.send(500,{error:"database error"})
      let allDate = [];
      result.forEach(data=>{
        allDate.push(data.time)
      })
      res.send(allDate)
    }
      res.end()
    })
 
  }

};

